import re


_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_ADDRESS_RE = re.compile(
    r"((?:北京市|天津市|上海市|重庆市|"
    r"[\u4e00-\u9fff]{2,8}(?:省|自治区))"
    r"[\u4e00-\u9fff]{1,12}(?:市|州|盟|地区)"
    r".{0,80}?"
    r"(?:\d+(?:栋|幢|号楼|座)\d+单元\d{1,5}(?:室|号)?|"
    r"\d+(?:栋|幢|号楼|座)\d{1,5}(?:室|号)?|"
    r"\d+组团\d+(?:栋|幢|号楼|座)(?:\d+单元)?\d{1,5}(?:室|号)?|"
    r"\d+(?:号|室)))",
    re.IGNORECASE,
)
_FAULT_RE = re.compile(
    r"((?:冰箱|冰柜|空调|洗衣机|电视|热水器|油烟机|燃气灶|"
    r"微波炉|洗碗机|烘干机|净水器|饮水机)"
    r".{0,8}?"
    r"(?:不制冷|不制热|不启动|不工作|不通电|不排水|不进水|"
    r"不脱水|不点火|不加热|漏水|漏电|异响|噪音大|显示异常|故障))"
)
_NAME_LABEL_RE = re.compile(
    r"(?:客户姓名|联系人|姓名|客户)\s*[:：]?\s*([\u4e00-\u9fff·]{2,8})"
)
_ADDRESS_LABEL_RE = re.compile(
    r"(?:详细地址|地址)\s*[:：]?\s*(.+?)(?=(?:联系电话|电话|客户姓名|"
    r"联系人|姓名|故障类型|故障描述)\s*[:：]|[\r\n]|$)"
)
_FAULT_LABEL_RE = re.compile(
    r"(?:故障类型|故障描述|故障)\s*[:：]?\s*(.+?)(?=(?:联系电话|电话|"
    r"详细地址|地址|客户姓名|联系人|姓名)\s*[:：]|[\r\n]|$)"
)


def _clean(value):
    return (value or "").strip(" \t\r\n,，。;；:：|-")


def _remove_once(text, value):
    return text.replace(value, " ", 1) if value else text


def parse_task_text(text):
    """从任务自由文本派生客户字段；不修改或持久化原始任务。"""
    source = str(text or "")
    result = {
        "contact_phone": "",
        "detailed_address": "",
        "customer_name": "",
        "fault_type": "",
    }
    if not source.strip():
        return result

    phone_match = _PHONE_RE.search(source)
    if phone_match:
        result["contact_phone"] = phone_match.group(1)

    address_match = _ADDRESS_LABEL_RE.search(source) or _ADDRESS_RE.search(source)
    if address_match:
        result["detailed_address"] = _clean(address_match.group(1))

    fault_match = _FAULT_LABEL_RE.search(source) or _FAULT_RE.search(source)
    if fault_match:
        result["fault_type"] = _clean(fault_match.group(1))

    name_match = _NAME_LABEL_RE.search(source)
    if name_match:
        result["customer_name"] = _clean(name_match.group(1))
    else:
        residual = source
        for value in (
            result["contact_phone"],
            result["detailed_address"],
            result["fault_type"],
        ):
            residual = _remove_once(residual, value)
        residual = re.sub(
            r"(?:联系电话|电话|详细地址|地址|客户姓名|联系人|姓名|"
            r"故障类型|故障描述|故障)\s*[:：]?",
            " ",
            residual,
        )
        candidates = re.findall(r"(?<![\u4e00-\u9fff])([\u4e00-\u9fff·]{2,4})(?![\u4e00-\u9fff])", residual)
        if candidates:
            result["customer_name"] = candidates[0]

    return result
