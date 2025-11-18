import copy
import pandas as pd
from datetime import datetime


# ============================================================
# ИНИЦИАЛИЗАЦИЯ ЛОГОВ
# ============================================================

def init_logs(session_state):
    """
    Создаёт массив log_actions, если его нет.
    """
    if "log_actions" not in session_state:
        session_state["log_actions"] = []


# ============================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ: ТЕКУЩИЙ TIMESTAMP
# ============================================================

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# 🧾 ДОБАВИТЬ ЗАПИСЬ В ЛОГ
# ============================================================

def log_action(
    session_state,
    action: str,
    manager_id: str = None,
    row_id=None,
    column_name=None,
    old_value=None,
    new_value=None,
    extra: dict = None,
):
    """
    Универсальная функция логирования.
    """

    entry = {
        "date": now(),
        "action": action,               # edit_cell, delete_row, rename_column...
        "manager_id": manager_id,
        "row_id": row_id,               # Activity Master Number или None
        "column_name": column_name,
        "old_value": copy.deepcopy(old_value),
        "new_value": copy.deepcopy(new_value),
    }

    # кастомные поля
    if extra:
        entry.update(extra)

    session_state["log_actions"].append(entry)


# ============================================================
# ЛОГИРОВАНИЕ СПЕЦИФИЧЕСКИХ ТИПОВ
# ============================================================

def log_edit_cell(session_state, manager_id, row_id, column_name, old_value, new_value):
    log_action(
        session_state,
        action="edit_cell",
        manager_id=manager_id,
        row_id=row_id,
        column_name=column_name,
        old_value=old_value,
        new_value=new_value,
    )


def log_delete_row(session_state, manager_id, row_id, old_row_dict):
    log_action(
        session_state,
        action="delete_row",
        manager_id=manager_id,
        row_id=row_id,
        old_value=old_row_dict,
        new_value=None,
    )


def log_rename_column(session_state, manager_id, old_name, new_name):
    log_action(
        session_state,
        action="rename_column",
        manager_id=manager_id,
        column_name=old_name,
        old_value=old_name,
        new_value=new_name,
    )


def log_delete_column(session_state, manager_id, col_name):
    log_action(
        session_state,
        action="delete_column",
        manager_id=manager_id,
        column_name=col_name,
        old_value=col_name,
        new_value=None,
    )


def log_add_column(session_state, manager_id, col_name):
    log_action(
        session_state,
        action="add_column",
        manager_id=manager_id,
        column_name=col_name,
        old_value=None,
        new_value=col_name,
    )


def log_undo(session_state, manager_id):
    log_action(
        session_state,
        action="undo_action",
        manager_id=manager_id,
    )


def log_redo(session_state, manager_id):
    log_action(
        session_state,
        action="redo_action",
        manager_id=manager_id,
    )


# ============================================================
# ПОЛУЧИТЬ ЛОГИ В ВИДЕ DATAFRAME
# ============================================================

def get_logs_df(session_state) -> pd.DataFrame:
    """
    Преобразует log_actions → DataFrame.
    """
    return pd.DataFrame(session_state.get("log_actions", []))


# ============================================================
# ОЧИСТИТЬ ВСЕ ЛОГИ
# ============================================================

def clear_logs(session_state):
    session_state["log_actions"] = []
