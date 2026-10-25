from __future__ import annotations

import re


DELETE_TERMS = (
    r"delet", r"eras", r"clos(?:e|ed|ing|ure)", r"remov", r"get rid of",
    r"forget me", r"wipe", r"gone", r"suppression", r"supprim", r"effac",
    r"elimin", r"borr", r"exclus[aã]o", r"lösch", r"entfern", r"usun",
    r"删除", r"清除", r"削除", r"消去", r"삭제", r"탈퇴",
)

DELETE_SCOPE = (
    r"account", r"profile", r"personal (?:data|information|details)", r"my data",
    r"my information", r"records? (?:linked|tied)", r"every trace", r"anything .*me",
    r"compte", r"données", r"informations? personnelles?", r"cuenta", r"conta",
    r"datos", r"dados", r"informaci[oó]n personal", r"konto", r"daten",
    r"personenbezogen", r"konto", r"dane", r"账户", r"帐号", r"账号",
    r"数据", r"个人信息", r"アカウント", r"データ", r"個人情報",
    r"계정", r"데이터", r"개인",
)

# Remove only the negated deletion expression. A later positive clause still
# authorizes deletion ("delete my account; do not close other accounts").
NEGATED_DELETE = (
    r"(?:do not|don't|don’t|not asking (?:you )?to|please don't)\s+(?:want to\s+)?(?:close|delete|erase|remove)",
    r"without\s+(?:closing|deleting|erasing|removing)",
    r"ne\s+(?:me\s+)?(?:supprim\w*|effac\w*)\s+pas",
    r"no\s+(?:borre\w*|elimine\w*)", r"nicht\s+(?:lösch\w*|entfern\w*)",
    r"(?:lösch\w*|entfern\w*).{0,20}\bnicht\b", r"不要(?:删除|清除)",
    r"(?:削除|消去)しない", r"(?:삭제|탈퇴)하지\s*마",
    r"not (?:a request|asking) (?:for|to) (?:account )?(?:deletion|erase\w*)",
)

FIELD_ONLY = (
    r"remove my (?:phone|telephone|email)(?: number| address)?",
    r"remove (?:the )?(?:phone|telephone|email)(?: number| address)? from my profile",
    r"remove me from marketing lists? only", r"marketing lists? only", r"unsubscribe",
    r"reset(?:ting)? the login",
    r"change the email", r"correct (?:it|my data)",
)


def deletion_intent(text: str) -> bool:
    value = " ".join(text.casefold().split())
    for pattern in NEGATED_DELETE + FIELD_ONLY:
        value = re.sub(pattern, " ", value)
    has_deletion = any(re.search(pattern, value) for pattern in DELETE_TERMS)
    has_scope = any(re.search(pattern, value) for pattern in DELETE_SCOPE)
    return has_deletion and has_scope
