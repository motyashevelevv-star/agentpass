"use client";
import { useEffect, useRef, useState } from 'react';
import { registerStepUp, ApiError } from '@/lib/api';
import { Modal } from './ui/dialog';
import { Button } from './ui/button';

export function StepUp() {
  const [open, setOpen] = useState(false);
  const pending = useRef<{resolve:(code:string)=>void;reject:(error:Error)=>void}|null>(null);
  function cancel() {
    pending.current?.reject(new ApiError('STEP_UP_CANCELLED','Подтверждение отменено',403));
    pending.current=null;
    setOpen(false);
  }
  useEffect(() => {
    registerStepUp(() => new Promise<string>((resolve,reject) => {
      if (pending.current) { reject(new Error('Завершите текущее подтверждение')); return; }
      pending.current={resolve,reject}; setOpen(true);
    }));
    return () => { registerStepUp(null); pending.current?.reject(new Error('Окно закрыто')); };
  },[]);
  return <Modal open={open} onOpenChange={cancel} title="Подтвердите действие" description="Введите новый код приложения-аутентификатора. Уже использованный код не принимается.">
    <form className="form-stack" onSubmit={e=>{
      e.preventDefault();
      const code=String(new FormData(e.currentTarget).get('code'));
      pending.current?.resolve(code); pending.current=null; setOpen(false);
    }}>
      <label>Одноразовый код<input name="code" inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" required autoFocus /></label>
      <div className="form-footer"><Button type="button" variant="outline" onClick={cancel}>Отмена</Button><Button>Подтвердить</Button></div>
    </form>
  </Modal>;
}
