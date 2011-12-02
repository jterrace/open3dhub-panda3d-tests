import sys
import numpy
import matplotlib.pyplot as plt
from matplotlib import rc, rcParams
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties

rc('text', usetex=True)
rc('font', family='serif')

orig_fps = []
orig_unflat = []
base_fps = []
prog_full = []
f = open('throughput_results.txt', 'r')
for line in f:
    nums = line.strip().split(' ')
    if len(nums) < 4:
        continue
    orig_fps.append(float(nums[0]))
    orig_unflat.append(float(nums[1]))
    base_fps.append(float(nums[2]))
    prog_full.append(float(nums[3]))

#improvements = [(b-o) / o for o,b in zip(orig_fps, base_fps)]
#print 'min', numpy.min(improvements)
#print 'max', numpy.max(improvements)
#print 'mean', numpy.mean(improvements)
#print 'median', numpy.median(improvements)

#together_sorted = sorted(zip(orig_fps, base_fps))
#orig_fps = [x for x,y in together_sorted]
#base_fps = [y for x,y in together_sorted]

x_vals = numpy.arange(0, 1, 1.0 / len(orig_fps))
fig = plt.figure(figsize=(4,2))
ax = fig.add_subplot(1,1,1)
#ax.set_yscale('symlog')
ax.scatter(x_vals,sorted(orig_fps),color='b', marker='+', s=2, linewidth=0.2)
ax.scatter(x_vals,sorted(base_fps),color='r', marker='x', s=2, linewidth=0.2)
ax.scatter(x_vals,sorted(orig_unflat),color='g', marker='o', s=2, linewidth=0.2)
ax.scatter(x_vals,sorted(prog_full),color='k', marker='s', s=2, linewidth=0.2)
plt.ylim(0,max(base_fps))
plt.xlim(0, 1)
#ax.set_title('Change in Download Size for First Display')

p1 = Line2D([0],[1], color="r", linewidth=2)
p2 = Line2D([0],[1], color="k", linewidth=2)
p3 = Line2D([0],[1], color="b", linewidth=2)
p4 = Line2D([0],[1], color="g", linewidth=2)
prop = FontProperties(size=7)
plt.legend((p1, p2, p3, p4), ['Base Progressive', 'Full Progressive', 'Original Flattened', 'Original'], loc=4, prop=prop)

ax.set_xlabel('Mesh')
ax.set_ylabel('Frames Per Second')
plt.gcf().subplots_adjust(bottom=0.24, left=0.14, right=0.95, top=0.98)
plt.savefig('fps_graph.png', format='png', dpi=150)
