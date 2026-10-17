"""素材风险标记:带这些标记的镜头不会被选中。

默认是"商场促销类"的一套;别的项目在 project.json 里写 "risk_tags": [...] 会**整体替换**默认值,
打标时(templates/tag_schema.json)risk 字段只能取这里的标签原文。
"""
from config import PROJECT

DEFAULT = ('路人或儿童正脸', '含明星肖像(版权肖像风险)', '品牌自带折扣牌(与全场2折起不同)', '拍摄者手指入镜', '画面虚焦/构图差', '第二位出镜者正脸',
           '汉堡节招牌可见(与国庆不符)')

BAD = tuple(PROJECT['risk_tags']) if PROJECT.get('risk_tags') else DEFAULT
