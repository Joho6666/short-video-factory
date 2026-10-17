"""素材风险标记(出现这些标记的镜头不会被选中)。新项目可在 project.json 的 risk_tags 里追加。"""
from config import PROJECT

BAD = ('路人或儿童正脸', '含明星肖像(版权肖像风险)', '品牌自带折扣牌(与全场2折起不同)', '拍摄者手指入镜', '画面虚焦/构图差', '第二位出镜者正脸',
       '汉堡节招牌可见(与国庆不符)') + tuple(PROJECT.get('risk_tags', []))
