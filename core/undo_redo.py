# core/undo_redo.py
import pandas as pd
from copy import deepcopy


def init_undo_redo(state):
    """Инициализация стеков undo/redo."""
    if "undo_stack" not in state:
        state["undo_stack"] = []
    if "redo_stack" not in state:
        state["redo_stack"] = []


def push_undo_state(state, df, logs):
    """Сохраняет текущее состояние перед изменением."""
    state["undo_stack"].append((deepcopy(df), deepcopy(logs)))
    state["redo_stack"].clear()


def undo(state):
    """Возврат к предыдущему состоянию."""
    if not state["undo_stack"]:
        return None

    prev_df, prev_logs = state["undo_stack"].pop()
    state["redo_stack"].append((deepcopy(state["merged_df"]), deepcopy(state["log_actions"])))

    state["merged_df"] = deepcopy(prev_df)
    state["log_actions"] = deepcopy(prev_logs)

    return prev_df


def redo(state):
    """Повтор действия."""
    if not state["redo_stack"]:
        return None

    next_df, next_logs = state["redo_stack"].pop()
    state["undo_stack"].append((deepcopy(state["merged_df"]), deepcopy(state["log_actions"])))

    state["merged_df"] = deepcopy(next_df)
    state["log_actions"] = deepcopy(next_logs)

    return next_df
