import { readFile } from "node:fs/promises";
import { createHmac, randomUUID } from 'node:crypto';
import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
async function login(page: Page, email = "demo@agentpass.local") {
  // Separate real account per test: financial history and rate limits do not leak between cases.
  if (email === "demo@agentpass.local") {
    email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
    const registration={data: {
        email,
        password: process.env.DEMO_PASSWORD || "AgentPass-demo-2026!",
        name: "E2E User",
        organization_name: "E2E Workspace",
      }};
    let response = await page.request.post("/api/v1/auth/register", registration);
    if(response.status()===429){
      // Exercise real rate limits; a larger suite can cross the five/minute window.
      test.setTimeout(120000);
      await page.waitForTimeout(Math.min(60000,Number(response.headers()['retry-after'] || 60)*1000));
      response=await page.request.post('/api/v1/auth/register',registration);
    }
    expect(response.status()).toBe(201);
  }
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "AgentPass-demo-2026!");
  await page.getByRole("button", { name: "Войти в AgentPass" }).click();
  await expect(page).toHaveURL(/overview/);
  await expect(
    page.getByRole("heading", { name: "Обзор", exact: true }),
  ).toBeVisible();
}
test("три решения, согласие, исполнение и история через общий backend", async ({
  page,
  context,
}) => {
  await login(page);
  await page.goto("/console");
  await page.getByRole("button", { name: "Новый демо-бюджет" }).click();
  await expect(page.getByRole("status")).toContainText("Созданы новый агент");
  await page
    .getByRole("button", { name: "Наушники до 8 000 ₽", exact: true })
    .click();
  await expect(
    page.getByText("Покупка симулирована", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".result-explanation")).toContainText(
    "Операция соответствует всем правилам",
  );
  await page
    .getByRole("button", { name: "Наушники до 12 000 ₽", exact: true })
    .click();
  await expect(page.getByText("Ожидаю вашего согласия")).toBeVisible();
  const approvals = await context.newPage();
  await approvals.goto("/approvals");
  const card = approvals
    .locator(".approval-list .panel")
    .filter({ hasText: "Sony WH-CH720N" })
    .first();
  await card.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await expect(
    page.getByText("Покупка симулирована", { exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.locator(".result-explanation")).toContainText(
    "Реальных списаний нет",
  );
  await approvals.close();
  await page
    .getByRole("button", { name: "Наушники до 18 000 ₽", exact: true })
    .click();
  await expect(page.locator(".result-explanation")).toContainText(
    "Превышен лимит одной операции",
  );
  await expect(
    page.getByText("Операция не исполнена", { exact: true }),
  ).toBeVisible();
  await page.goto("/transactions");
  await expect(
    page.getByRole("button", { name: "Marshall Major V", exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "DENY", exact: true }).click();
  await expect(page.locator("tbody .badge").first()).toContainText("DENY");
});
test("создание агента, изменение и отзыв мандата", async ({ page }) => {
  await login(page);
  await page.goto("/agents");
  await page
    .getByRole("button", { name: "Подключить агента", exact: true })
    .first()
    .click();
  await page
    .getByLabel("Название", { exact: true })
    .fill("E2E Shopping " + Date.now());
  await page.getByLabel("Описание", { exact: true }).fill("E2E agent");
  await page
    .getByRole("button", { name: "Зарегистрировать", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.goto("/mandates?create=1");
  await page
    .getByLabel("Название мандата", { exact: true })
    .fill("E2E Mandate " + Date.now());
  const name = await page
    .getByLabel("Название мандата", { exact: true })
    .inputValue();
  await page
    .getByRole("button", { name: "Создать мандат", exact: true })
    .last()
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  const card = page.locator(".mandate-grid .panel").filter({ hasText: name });
  await card.getByRole("button", { name: "Изменить", exact: true }).click();
  await page
    .getByLabel("Лимит одной операции, ₽", { exact: true })
    .fill("9000");
  await page.getByRole("button", { name: "Сохранить правила" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(card).toContainText("v2");
  await page.goto("/developer/playground");
  await page
    .getByRole("combobox", { name: "Мандат", exact: true })
    .selectOption({ label: name + " · v2" });
  await page.getByLabel("Сумма, ₽", { exact: true }).fill("18000");
  await page.getByRole("button", { name: "Отправить запрос" }).click();
  await expect(page.locator(".json-output")).toContainText(
    "PER_TRANSACTION_LIMIT",
  );
  await page.getByLabel("Сумма, ₽", { exact: true }).fill("8000");
  await page
    .getByRole("button", { name: "Создать Intent", exact: true })
    .click();
  const editor = page.getByRole("textbox", { name: "JSON body" });
  const payload = JSON.parse(await editor.inputValue());
  payload.description = "\t=1+1";
  await editor.fill(JSON.stringify(payload, null, 2));
  await page.getByRole("button", { name: "Отправить запрос" }).click();
  await expect(page.locator(".json-output")).toContainText("authorized");
  await page.goto("/transactions");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Экспорт страницы" }).click();
  const download = await downloadPromise;
  const csv = await readFile((await download.path())!, "utf8");
  expect(csv).toContain("'\t=1+1");
  await page.goto("/mandates");
  await card.getByRole("button", { name: "Отозвать", exact: true }).click();
  await page
    .getByRole("button", { name: "Отозвать мандат", exact: true })
    .click();
  await expect(card).toContainText("Отозван");
});
test("все основные страницы, темы и мобильное меню", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  for (const [path, title] of [
    ["/agents", "Мои агенты"],
    ["/mandates", "Мандаты"],
    ["/transactions", "Операции"],
    ["/approvals", "Подтверждения"],
    ["/analytics", "Аналитика"],
    ["/security", "Безопасность"],
    ["/settings", "Настройки"],
    ["/developer", "Developer Portal"],
    ["/developer/projects", "Developer Portal"],
    ["/developer/keys", "Developer Portal"],
    ["/developer/playground", "Developer Portal"],
    ["/developer/requests", "Developer Portal"],
    ["/developer/webhooks", "Developer Portal"],
    ["/developer/docs", "Developer Portal"],
    ["/developer/organizations", "Developer Portal"],
    ["/console", "Agent Console"],
  ]) {
    await page.goto(path);
    await expect(
      page.getByRole("heading", { name: title, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".loading")).toHaveCount(0);
  }
  await page.goto("/overview");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Тёмная тема", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(
    (
      await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze()
    ).violations,
  ).toEqual([]);
  await page.getByRole("button", { name: "Светлая тема", exact: true }).click();
  await page.goto("/developer/organizations");
  await page
    .getByRole("button", { name: "Создать организацию", exact: true })
    .click();
  const orgName = "E2E New Org " + Date.now();
  await page
    .getByRole("dialog")
    .getByLabel("Название", { exact: true })
    .fill(orgName);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Создать", exact: true })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.locator(".workspace-switch").click();
  await page.getByRole("menuitem", { name: orgName, exact: true }).click();
  await expect(page.locator(".workspace-switch")).toContainText(orgName);
  await page.goto("/overview");
  await expect(
    page.getByRole("heading", { name: "Обзор", exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Открыть меню" }).click();
  await page
    .locator(".sidebar")
    .getByRole("link", { name: "Мои агенты", exact: true })
    .click();
  await expect(page).toHaveURL(/agents/);
  expect(errors).toEqual([]);
});
test("административный RBAC и мониторинг", async ({ page }) => {
  await login(page);
  await page.goto("/admin");
  await expect(page.locator(".error-message")).toContainText(
    "только администратору",
  );
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("admin@agentpass.local");
  await page
    .getByLabel("Пароль", { exact: true })
    .fill(process.env.DEMO_PASSWORD || "AgentPass-demo-2026!");
  await page.getByRole("button", { name: "Войти в AgentPass" }).click();
  await expect(page).toHaveURL(/overview/);
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "Техническое состояние" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Организации", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Организации платформы" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "API и ошибки", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Журнал API-запросов" }),
  ).toBeVisible();
});

test("настоящая доставка webhook и локальная проверка подписи", async ({
  page,
}) => {
  await login(page);
  await page.goto("/developer/webhooks");
  await page
    .getByRole("button", { name: "Добавить endpoint", exact: true })
    .first()
    .click();
  await page
    .getByLabel("Название", { exact: true })
    .fill("E2E Receiver " + Date.now());
  await page
    .getByRole("button", { name: "Использовать локальный receiver" })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Добавить endpoint", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Сохраните секрет подписи" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Сохранён", exact: true }).click();
  await page
    .locator(".webhook-list>div")
    .first()
    .getByRole("button", { name: "Тест", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Получено sandbox receiver" }),
  ).toBeVisible({ timeout: 25000 });
  await expect(
    page.locator("tbody").filter({ hasText: "sandbox.test" }).last(),
  ).toContainText("APPROVE");
});

test('быстрый вход даёт все четыре интерфейса через серверную авторизацию',async({page})=>{
  await page.goto('/login');
  await page.getByRole('button',{name:'Открыть полный sandbox',exact:true}).click();
  await expect(page).toHaveURL(/overview/);
  await expect(page.getByRole('heading',{name:'Обзор',exact:true})).toBeVisible();
  for(const [path,title] of [['/agents','Мои агенты'],['/developer','Developer Portal'],['/console','Agent Console'],['/admin','Admin Console']]){
    await page.goto(path);
    await expect(page.getByRole('heading',{name:title,exact:true})).toBeVisible();
    await expect(page.locator('.loading')).toHaveCount(0);
    await expect(page.locator('.error-message')).toHaveCount(0);
  }
});

test('одноразовый grant, worker и жизненный цикл в истории',async({page,context})=>{
  await login(page);
  const csrf=(await context.cookies()).find(c=>c.name==='ap_csrf')!.value;
  const headers={'X-CSRF-Token':csrf};
  const demo=await page.request.post('/api/v1/sandbox/demo',{headers});
  expect(demo.status()).toBe(201);
  const {agent,mandate}=await demo.json();
  const created=await page.request.post('/api/v1/intents',{headers,data:{agent_id:agent.id,mandate_id:mandate.id,
    merchant:'Soundstore',merchant_id:'catalog:soundstore',order_id:randomUUID(),category:'electronics',amount:800000,currency:'RUB',
    description:'E2E execution grant',idempotency_key:randomUUID(),timestamp:new Date().toISOString(),structured_metadata:{test:true}}});
  expect(created.status()).toBe(201);
  const intent=await created.json();
  const grantResponse=await page.request.post(`/api/v1/intents/${intent.id}/execution-grant`,{headers,data:{}});
  expect(grantResponse.status()).toBe(200);
  const grant=await grantResponse.json();
  const a=await page.request.post('/api/v1/executions',{headers,data:{grant_token:grant.grant_token}});
  const b=await page.request.post('/api/v1/executions',{headers,data:{grant_token:grant.grant_token}});
  expect((await a.json()).id).toBe((await b.json()).id);
  await page.goto('/transactions');
  await page.getByRole('button',{name:'E2E execution grant',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog).toContainText('Подтверждено провайдером',{timeout:25000});
  await expect(dialog).toContainText('Локальная симуляция');
  const downloaded=page.waitForEvent('download');
  await dialog.getByRole('button',{name:'Экспорт деталей JSON'}).click();
  const file=await downloaded;
  const evidence=JSON.parse(await readFile((await file.path())!,'utf8'));
  expect(evidence.execution.status).toBe('succeeded');
  expect(evidence.transaction.status).toBe('simulated');
  expect(evidence).not.toHaveProperty('grant_token');
});

test('MFA подключается и защищает выпуск ключа исполнителя',async({page})=>{
  await login(page);
  await page.goto('/console');
  await page.getByRole('button',{name:'Новый демо-бюджет'}).click();
  await expect(page.getByRole('status')).toContainText('Созданы новый агент');
  await page.goto('/security');
  const panel=page.locator('.panel').filter({has:page.getByRole('heading',{name:'Двухфакторная аутентификация'})});
  await panel.getByLabel('Текущий пароль',{exact:true}).fill(process.env.DEMO_PASSWORD || 'AgentPass-demo-2026!');
  await panel.getByRole('button',{name:'Настроить MFA'}).click();
  await expect(panel.locator('.secret-box code')).toBeVisible();
  const secret=(await panel.locator('.secret-box code').textContent())!;
  function totp(counter:number){
    const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
    const bits=[...secret].map(c=>alphabet.indexOf(c).toString(2).padStart(5,'0')).join('');
    const bytes=Buffer.from(bits.match(/.{8}/g)!.map(x=>parseInt(x,2)));
    const message=Buffer.alloc(8);message.writeBigUInt64BE(BigInt(counter));
    const digest=createHmac('sha1',bytes).update(message).digest();const offset=digest[19]&15;
    return String((digest.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');
  }
  const counter=Math.floor(Date.now()/30000);
  await panel.getByLabel('Код из приложения').fill(totp(counter));
  await panel.getByRole('button',{name:'Подключить MFA',exact:true}).click();
  await expect(panel).toContainText('Приложение-аутентификатор подключено');
  await page.goto('/developer/keys');
  await page.getByRole('button',{name:'Создать ключ',exact:true}).click();
  await page.getByRole('dialog').getByLabel('Название',{exact:true}).fill('MFA E2E executor');
  await page.getByRole('dialog').getByRole('combobox',{name:'Агент',exact:true}).selectOption({index:1});
  await page.getByRole('dialog').getByRole('combobox',{name:'Назначение',exact:true}).selectOption('executor');
  await page.getByRole('button',{name:'Создать API-ключ',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Подтвердите действие'})).toBeVisible();
  const step=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:'Подтвердите действие'})});
  await step.getByLabel('Одноразовый код',{exact:true}).fill(totp(counter+1));
  await step.getByRole('button',{name:'Подтвердить',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Сохраните API-ключ'})).toBeVisible();
  await page.getByRole('button',{name:'Сохранён',exact:true}).click();
  await expect(page.locator('tbody')).toContainText('Доверенный исполнитель');
});
