"""Official YooKassa TEST checkout adapter. External connectivity NOT VERIFIED.

No stored payment method or autonomous account debit is used. Notifications are
untrusted hints; official documentation requires authenticating object status/IP,
not an invented HMAC header. AgentPass always refetches through authenticated API.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from urllib.parse import urlsplit, quote
import httpx
from .base import PaymentRequest, ProviderPayment, PaymentStatus, ProviderError
from .local import request_hash


class YooKassaSandbox:
    name = 'yookassa_sandbox'
    def __init__(self, shop_id, secret_key, return_url, client=None):
        if not shop_id or not secret_key.startswith('test_'):
            raise ProviderError('LIVE_CREDENTIALS_FORBIDDEN')
        if urlsplit(return_url).scheme != 'https':
            raise ProviderError('INVALID_RETURN_URL')
        self.shop_id, self.return_url = shop_id, return_url
        self.client = client or httpx.Client(base_url='https://api.yookassa.ru/v3/',
            auth=httpx.BasicAuth(shop_id,secret_key),timeout=5,follow_redirects=False)

    @staticmethod
    def _id(value):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',value):
            raise ProviderError('INVALID_PROVIDER_ID')
        return quote(value,safe='')

    def _http(self,method,path,key=None,body=None):
        if key and len(key)>64:
            raise ProviderError('INVALID_PROVIDER_IDEMPOTENCY_KEY')
        try:
            response=self.client.request(method,path,headers={'Idempotence-Key':key} if key else {},json=body)
            if response.status_code>=400 or response.is_redirect:
                raise ProviderError('PROVIDER_HTTP_'+str(response.status_code))
            value=response.json()
            if not isinstance(value,dict):
                raise ValueError
            return value
        except (httpx.HTTPError,ValueError):
            raise ProviderError('PROVIDER_UNAVAILABLE') from None

    @staticmethod
    def _minor(amount):
        try:
            value=Decimal(amount['value'])*100
            if not value.is_finite() or value!=value.to_integral_value() or not 0<value<=100_000_000_000:
                raise ValueError
            return int(value),amount['currency']
        except (KeyError,ValueError,TypeError,InvalidOperation):
            raise ProviderError('INVALID_PROVIDER_AMOUNT') from None

    def _parse(self,data):
        if data.get('test') is not True or data.get('recipient',{}).get('account_id')!=self.shop_id:
            raise ProviderError('PROVIDER_TEST_SHOP_MISMATCH')
        amount,currency=self._minor(data.get('amount',{}))
        metadata=data.get('metadata',{})
        fingerprint=metadata.get('agentpass_request_hash')
        if not isinstance(fingerprint,str) or not re.fullmatch(r'[a-f0-9]{64}',fingerprint):
            raise ProviderError('PROVIDER_BINDING_MISSING')
        status={'pending':PaymentStatus.PENDING,'waiting_for_capture':PaymentStatus.AUTHORIZED,
                'succeeded':PaymentStatus.SUCCEEDED,'canceled':PaymentStatus.CANCELLED}.get(data.get('status'),PaymentStatus.UNKNOWN)
        if status==PaymentStatus.SUCCEEDED and data.get('paid') is not True:
            status=PaymentStatus.UNKNOWN
        confirmation=data.get('confirmation',{}).get('confirmation_url')
        if confirmation:
            url=urlsplit(confirmation)
            if url.scheme!='https' or url.username or url.fragment or url.port not in (None,443) or url.hostname not in ('yoomoney.ru','yookassa.ru'):
                raise ProviderError('UNSAFE_CONFIRMATION_URL')
        payment_id=self._id(data.get('id'))
        return ProviderPayment(payment_id=payment_id,status=status,amount=amount,currency=currency,
            request_hash=fingerprint,receipt=('YKTEST-'+payment_id) if status==PaymentStatus.SUCCEEDED else None,
            confirmation_url=confirmation,test=True)

    def create_payment_intent(self,request:PaymentRequest,idempotency_key):
        if request.merchant_id!='yookassa:'+self.shop_id or not request.order_id or request.currency!='RUB':
            raise ProviderError('PROVIDER_MERCHANT_ORDER_MISMATCH')
        body={'amount':{'value':f'{Decimal(request.amount)/100:.2f}','currency':request.currency},
              'capture':True,'confirmation':{'type':'redirect','return_url':self.return_url},
              'description':request.description[:128],
              'metadata':{'agentpass_intent_id':request.intent_id,'agentpass_order_id':request.order_id,
                          'agentpass_request_hash':request_hash(request)}}
        return self._parse(self._http('POST','payments',idempotency_key,body))

    def authorize_test_payment(self,payment_id,idempotency_key):
        raise ProviderError('USER_CHECKOUT_REQUIRED')

    def get_payment_status(self,payment_id):
        return self._parse(self._http('GET','payments/'+self._id(payment_id)))

    def reconcile(self,payment_id,idempotency_key):
        if not payment_id:
            # The provider has no documented lookup by our idempotency key. NEVER
            # create another checkout after an ambiguous timeout/expired provider key.
            raise ProviderError('PROVIDER_ID_UNKNOWN_REQUIRES_CALLBACK')
        return self.get_payment_status(payment_id)

    def cancel(self,payment_id,idempotency_key):
        return self._parse(self._http('POST','payments/'+self._id(payment_id)+'/cancel',idempotency_key,{}))

    def refund(self,payment_id,idempotency_key):
        payment=self.get_payment_status(payment_id)
        if payment.status!=PaymentStatus.SUCCEEDED:
            raise ProviderError('PROVIDER_NOT_REFUNDABLE')
        result=self._http('POST','refunds',idempotency_key,{'payment_id':payment.payment_id,
            'amount':{'value':f'{Decimal(payment.amount)/100:.2f}','currency':payment.currency}})
        if result.get('payment_id')!=payment.payment_id or self._minor(result.get('amount',{}))!=(payment.amount,payment.currency):
            raise ProviderError('PROVIDER_REFUND_MISMATCH')
        if result.get('status')!='succeeded':
            raise ProviderError('PROVIDER_REFUND_UNCONFIRMED')
        return payment.model_copy(update={'status':PaymentStatus.REFUNDED})

    def handle_callback(self,headers,body):
        try:
            data=json.loads(body)
            if not isinstance(data,dict) or data.get('type')!='notification' or data.get('event') not in ('payment.succeeded','payment.canceled','payment.waiting_for_capture'):
                raise ValueError
            return self._id(data['object']['id'])
        except (ValueError,KeyError,TypeError):
            raise ProviderError('INVALID_PROVIDER_CALLBACK') from None
