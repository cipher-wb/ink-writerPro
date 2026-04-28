# tests/core/auto/_blueprint_fixtures.py
"""Shared fixtures producing minimal valid / invalid blueprints."""
from pathlib import Path


def write_full_blueprint(path: Path) -> None:
    path.write_text(
        """# 小说蓝本

## 一、项目元信息
### 平台
qidian

### 激进度档位
2

### 目标章数
600

### 目标字数


## 二、故事核心
### 书名
AUTO

### 题材方向
仙侠

### 核心卖点


### 核心冲突
弃徒带真凶回师门当众对峙

## 三、主角设定
### 主角姓名
AUTO

### 主角人设
寒门弟子，渴望师门认可；过度自尊不会服软

### 主角职业/身份


## 四、金手指
### 金手指类型
信息

### 能力一句话
每读懂他人遗书借走立遗嘱者绝学三天

### 主代价


### 第一章爽点预览


## 五、配角与情感线
### 女主/核心配角姓名
AUTO

### 女主/核心配角人设


## 六、前三章钩子
### 第 1 章钩子


### 第 2 章钩子


### 第 3 章钩子


## 七、可选高级字段
### 元规则倾向


### 商业安全边界打破


### 语言风格档位


### 禁忌/避坑提示


## 八、自由备注

""",
        encoding="utf-8",
    )


def write_minimal_blueprint(path: Path) -> None:
    """Has only required fields; everything else AUTO/empty."""
    path.write_text(
        """# 蓝本
## 一、项目元信息
### 平台
qidian
### 激进度档位
2
## 二、故事核心
### 题材方向
仙侠
### 核心冲突
弃徒带真凶回师门当众对峙
## 三、主角设定
### 主角人设
寒门弟子；过度自尊不会服软
## 四、金手指
### 金手指类型
信息
### 能力一句话
每读懂他人遗书借走立遗嘱者绝学三天
""",
        encoding="utf-8",
    )


def write_blueprint_missing_required(path: Path) -> None:
    """Missing 主角人设."""
    path.write_text(
        """# 蓝本
## 一、项目元信息
### 平台
qidian
## 二、故事核心
### 题材方向
仙侠
### 核心冲突
foo
## 三、主角设定
### 主角人设

## 四、金手指
### 金手指类型
信息
### 能力一句话
abc
""",
        encoding="utf-8",
    )


def write_blueprint_with_gf_blacklist_word(path: Path) -> None:
    path.write_text(
        """# 蓝本
## 一、项目元信息
### 平台
qidian
## 二、故事核心
### 题材方向
仙侠
### 核心冲突
foo
## 三、主角设定
### 主角人设
abc
## 四、金手指
### 金手指类型
信息
### 能力一句话
修为暴涨碾压一切
""",
        encoding="utf-8",
    )
