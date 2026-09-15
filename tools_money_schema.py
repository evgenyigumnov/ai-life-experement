"""Схемы денежных инструментов агента."""

MONEY_BALANCE_DESCRIPTION = (
    "Показать баланс агента. 1 единица = 1 следующий цикл/тик LLM без паузы "
    "перед ним; type=creativity включает TEMPERATURE=1.4 на следующий цикл. "
    "Адаптивное расписание без оплаченных единиц: 0 → 30 сек → 1 мин → "
    "2 мин → 5 мин → 10 мин → 20 мин → 40 мин → 1 час → 2 часа → 4 часа."
)
MONEY_SPEND_DESCRIPTION = (
    "Потратить единицы агента. type=speed покупает следующий цикл без паузы: "
    "1 единица покупает 1 следующий цикл без паузы, N единиц — N следующих "
    "циклов без пауз. type=creativity включает TEMPERATURE=1.4 на столько "
    "следующих циклов, сколько потрачено единиц. purpose — обязательное "
    "описание конкретной работы. Единицы не дают дополнительных итераций. "
    "Операция не меняет кошелёк при нехватке баланса."
)

MONEY_BALANCE_TOOL = {
    "type": "function",
    "function": {
        "name": "money_balance",
        "description": MONEY_BALANCE_DESCRIPTION,
        "parameters": {"type": "object", "properties": {}},
    },
}

MONEY_SPEND_TOOL = {
    "type": "function",
    "function": {
        "name": "money_spend",
        "description": MONEY_SPEND_DESCRIPTION,
        "parameters": {
            "type": "object",
            "properties": {
                "units": {
                    "type": "integer", "minimum": 1,
                    "description": "Положительное число единиц для следующих циклов",
                },
                "purpose": {
                    "type": "string",
                    "description": "Зачем нужна конкретная работа",
                },
                "type": {
                    "type": "string",
                    "enum": ["speed", "creativity"],
                    "description": "Эффект: отмена паузы или температура 1.4",
                },
            },
            "required": ["units", "purpose", "type"],
        },
    },
}

BALANCE_DESCRIPTION = MONEY_BALANCE_DESCRIPTION
SPEND_DESCRIPTION = MONEY_SPEND_DESCRIPTION
BALANCE_TOOL = MONEY_BALANCE_TOOL
SPEND_TOOL = MONEY_SPEND_TOOL
