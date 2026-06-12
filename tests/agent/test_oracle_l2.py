"""L2Oracle 单测——基于 accessibility tree XML 的状态断言。

覆盖三个案例：
1. 状态保留（pass）：旋转后输入框文本正确保留
2. 状态丢失（fail）：旋转后输入框文本被清空
3. 节点消失（fail）：旋转后目标节点从 accessibility tree 中消失
"""


from aiverify.agent.oracle import L2Oracle, Assertion, validate_verdict

# ---------------------------------------------------------------------------
# Fixtures：固定 XML（uiautomator dump 格式精简版）
# ---------------------------------------------------------------------------

# 旋转前：EditText 含文字 "hello world"，Checkbox 已勾选
XML_BEFORE = """\
<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" resource-id="com.example.app:id/root" class="android.widget.FrameLayout"
        text="" bounds="[0,0][1080,2340]">
    <node index="0" resource-id="com.example.app:id/input_field"
          class="android.widget.EditText"
          text="hello world" content-desc="输入框"
          bounds="[36,200][1044,300]" />
    <node index="1" resource-id="com.example.app:id/remember_checkbox"
          class="android.widget.CheckBox"
          text="" checked="true"
          bounds="[36,320][100,380]" />
  </node>
</hierarchy>
"""

# 旋转后（状态保留）：文本和勾选状态均保留
XML_AFTER_PRESERVED = """\
<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="1">
  <node index="0" resource-id="com.example.app:id/root" class="android.widget.FrameLayout"
        text="" bounds="[0,0][2340,1080]">
    <node index="0" resource-id="com.example.app:id/input_field"
          class="android.widget.EditText"
          text="hello world" content-desc="输入框"
          bounds="[36,200][2304,300]" />
    <node index="1" resource-id="com.example.app:id/remember_checkbox"
          class="android.widget.CheckBox"
          text="" checked="true"
          bounds="[36,320][100,380]" />
  </node>
</hierarchy>
"""

# 旋转后（状态丢失）：EditText 文本被清空，Checkbox 被重置为 false
XML_AFTER_LOST = """\
<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="1">
  <node index="0" resource-id="com.example.app:id/root" class="android.widget.FrameLayout"
        text="" bounds="[0,0][2340,1080]">
    <node index="0" resource-id="com.example.app:id/input_field"
          class="android.widget.EditText"
          text="" content-desc="输入框"
          bounds="[36,200][2304,300]" />
    <node index="1" resource-id="com.example.app:id/remember_checkbox"
          class="android.widget.CheckBox"
          text="" checked="false"
          bounds="[36,320][100,380]" />
  </node>
</hierarchy>
"""

# 旋转后（节点消失）：input_field 节点被完全移除
XML_AFTER_NODE_GONE = """\
<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="1">
  <node index="0" resource-id="com.example.app:id/root" class="android.widget.FrameLayout"
        text="" bounds="[0,0][2340,1080]">
    <node index="1" resource-id="com.example.app:id/remember_checkbox"
          class="android.widget.CheckBox"
          text="" checked="true"
          bounds="[36,320][100,380]" />
  </node>
</hierarchy>
"""

# 测试用断言
ASSERTIONS_TEXT: list[Assertion] = [
    {
        "resource_id": "com.example.app:id/input_field",
        "attr": "text",
        "expected": "hello world",
    }
]

ASSERTIONS_MULTI: list[Assertion] = [
    {
        "resource_id": "com.example.app:id/input_field",
        "attr": "text",
        "expected": "hello world",
    },
    {
        "resource_id": "com.example.app:id/remember_checkbox",
        "attr": "checked",
        "expected": "true",
    },
]

# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

oracle = L2Oracle()


def test_l2_pass_when_state_preserved():
    """旋转后文本保留 → outcome=pass。"""
    verdict = oracle.judge(
        XML_BEFORE,
        XML_AFTER_PRESERVED,
        ASSERTIONS_TEXT,
        trigger_steps=["旋转屏幕（portrait→landscape）"],
    )

    assert verdict["level"] == "L2"
    assert verdict["outcome"] == "pass"
    assert verdict["defect_class_hypothesis"] is None
    assert verdict["confidence"] > 0.5
    assert "旋转屏幕" in verdict["trigger_steps"][0]

    validate_verdict(verdict)


def test_l2_fail_when_state_lost():
    """旋转后文本丢失 → outcome=fail，evidence 含 state_diff。"""
    verdict = oracle.judge(
        XML_BEFORE,
        XML_AFTER_LOST,
        ASSERTIONS_TEXT,
        trigger_steps=["旋转屏幕（portrait→landscape）"],
    )

    assert verdict["level"] == "L2"
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "state_loss"
    assert verdict["confidence"] > 0.5

    # evidence 必须包含 state_diff 类型，且 ref 描述了差异
    assert verdict["evidence"], "fail 判定必须有证据"
    types = {e["type"] for e in verdict["evidence"]}
    assert "state_diff" in types

    refs = " ".join(e["ref"] for e in verdict["evidence"])
    assert "input_field" in refs
    assert "hello world" in refs

    validate_verdict(verdict)


def test_l2_fail_when_node_gone():
    """节点消失 → outcome=fail，evidence 说明节点消失。"""
    verdict = oracle.judge(
        XML_BEFORE,
        XML_AFTER_NODE_GONE,
        ASSERTIONS_TEXT,
        trigger_steps=["旋转屏幕"],
    )

    assert verdict["level"] == "L2"
    assert verdict["outcome"] == "fail"

    refs = " ".join(e["ref"] for e in verdict["evidence"])
    # 应提及节点消失
    assert "消失" in refs or "absent" in refs or "input_field" in refs

    validate_verdict(verdict)


def test_l2_multi_assertion_all_pass():
    """多条断言全部通过 → outcome=pass。"""
    verdict = oracle.judge(XML_BEFORE, XML_AFTER_PRESERVED, ASSERTIONS_MULTI)

    assert verdict["outcome"] == "pass"
    validate_verdict(verdict)


def test_l2_multi_assertion_partial_fail():
    """多条断言部分失败 → outcome=fail，所有失败断言均在 evidence 中。"""
    verdict = oracle.judge(XML_BEFORE, XML_AFTER_LOST, ASSERTIONS_MULTI)

    assert verdict["outcome"] == "fail"
    # 两条断言都失败（text 清空、checked 变 false），evidence 应有两条
    assert len(verdict["evidence"]) == 2

    validate_verdict(verdict)


def test_l2_empty_assertions_gives_pass():
    """无断言时视为通过（无需校验任何节点）。"""
    verdict = oracle.judge(XML_BEFORE, XML_AFTER_LOST, [])
    assert verdict["outcome"] == "pass"
    validate_verdict(verdict)


def test_l2_invalid_xml_gives_inconclusive():
    """XML 格式错误 → outcome=inconclusive。"""
    verdict = oracle.judge("<invalid>", XML_AFTER_PRESERVED, ASSERTIONS_TEXT)
    assert verdict["outcome"] == "inconclusive"
    validate_verdict(verdict)


def test_l2_verdict_id_format():
    """verdict_id 应以 'L2-' 开头。"""
    verdict = oracle.judge(XML_BEFORE, XML_AFTER_PRESERVED, [])
    assert verdict["verdict_id"].startswith("L2-")
