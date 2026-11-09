import { useCallback, useMemo } from "react";
import * as moneyApi from "../../api/money";
import { describeError } from "../../api/client";
import type { ExpensePatchIn } from "../../api/money";
import type { ExpenseOut } from "../../api/types";
import { useToast } from "../../ui/Toast";

export interface ExpenseActions {
  keep: (expenseId: string) => void;
  star: (expenseId: string, starred: boolean) => void;
  setVoid: (expense: ExpenseOut, isVoid: boolean) => void; // voiding offers Undo
  remove: (expense: ExpenseOut) => void; // deleting offers Undo (the restore route)
  edit: (expenseId: string, patch: ExpensePatchIn) => Promise<void>; // rejects: the edit row shows why
}

// What an expense row can do (Board redesign G9, absorbing Task 9). `reload` runs after every write and
// `onError` gets a plain sentence. Voiding and deleting each toast with Undo, which runs the reverse; an Undo the
// gateway refuses (its project is gone) says why in a danger toast.
export function useExpenseActions(reload: () => void, onError: (message: string) => void): ExpenseActions {
  const toast = useToast();
  const fail = useCallback((err: unknown) => onError(describeError(err)), [onError]);
  const undo = useCallback((request: Promise<unknown>) => {
    request.catch((err: unknown) => toast.show(describeError(err), { tone: "danger" })).finally(reload);
  }, [reload, toast]);

  const keep = useCallback((id: string) => { moneyApi.keepExpense(id).then(reload).catch(fail); }, [fail, reload]);
  const star = useCallback((id: string, starred: boolean) => {
    moneyApi.starExpense(id, starred).then(reload).catch(fail);
  }, [fail, reload]);
  const setVoid = useCallback((expense: ExpenseOut, isVoid: boolean) => {
    moneyApi.voidExpense(expense.id, isVoid)
      .then(() => {
        if (isVoid) {
          toast.show("Expense voided", { action: { label: "Undo", run: () => undo(moneyApi.voidExpense(expense.id, false)) } });
        }
        reload();
      })
      .catch(fail);
  }, [fail, reload, toast, undo]);
  const remove = useCallback((expense: ExpenseOut) => {
    moneyApi.deleteExpense(expense.id)
      .then(() => {
        toast.show("Expense deleted", { action: { label: "Undo", run: () => undo(moneyApi.restoreExpense(expense.id)) } });
        reload();
      })
      .catch(fail);
  }, [fail, reload, toast, undo]);
  const edit = useCallback(async (id: string, patch: ExpensePatchIn) => {
    await moneyApi.updateExpense(id, patch);
    reload();
  }, [reload]);
  return useMemo(() => ({ keep, star, setVoid, remove, edit }), [keep, star, setVoid, remove, edit]);
}
