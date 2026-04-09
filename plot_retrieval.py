import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

matplotlib.rcParams['font.family'] = 'SimHei'
matplotlib.rcParams['axes.unicode_minus'] = False

categories = ['景点详情', '路线推荐', '历史文化', '整体']
vector   = [100, 40, 60, 66.7]
graph    = [100, 60, 40, 66.7]
graphrag = [100, 80, 100, 93.3]

x = np.arange(len(categories))
width = 0.25

fig, ax = plt.subplots(figsize=(10, 6))

bars1 = ax.bar(x - width, vector,   width, label='纯向量检索', color='#5B9BD5')
bars2 = ax.bar(x,          graph,   width, label='纯图检索',   color='#ED7D31')
bars3 = ax.bar(x + width,  graphrag, width, label='GraphRAG混合', color='#70AD47')

ax.set_title('三种检索方法信息召回率对比', fontsize=14, pad=15)
ax.set_xlabel('问题类型', fontsize=12)
ax.set_ylabel('信息召回率 (%)', fontsize=12)
ax.set_xticks(x)
ax.set_xticklabels(categories, fontsize=11)
ax.set_ylim(0, 125)
ax.legend(fontsize=11, loc='upper right')
ax.yaxis.grid(True, linestyle='--', alpha=0.7)
ax.set_axisbelow(True)

for bar in bars1:
    h = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2, h + 1.5, f'{h}%', ha='center', va='bottom', fontsize=9)
for bar in bars2:
    h = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2, h + 1.5, f'{h}%', ha='center', va='bottom', fontsize=9)
for bar in bars3:
    h = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2, h + 1.5, f'{h}%', ha='center', va='bottom', fontsize=9)

plt.tight_layout()
plt.savefig('retrieval_comparison.png', dpi=300, bbox_inches='tight')
print("图已保存至 retrieval_comparison.png")
plt.show()
