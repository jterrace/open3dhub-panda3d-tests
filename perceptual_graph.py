import os
import sys
import pickle
import numpy
import matplotlib.pyplot as plt
from matplotlib import rc, rcParams
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import Formatter

CURDIR = os.path.abspath(os.path.dirname(__file__))

rc('text', usetex=True)
rc('font', family='serif')

class MyFormatter(Formatter):
    def __call__(self, val, idx):
        return "%dK" % (val / 1000.0)

prop = FontProperties(size=7)
data = pickle.load(open('perceptual_errors.pickle', 'rb'))

prog_x = numpy.array([d[0] for d in data['prog_errors']])
prog_y = numpy.array([d[1] for d in data['prog_errors']])

full_x = numpy.array([d[0] for d in data['full_errors']])
full_y = numpy.array([d[1] for d in data['full_errors']])

opt_x = numpy.array([d[0] for d in data['opt_errors']])
opt_y = numpy.array([d[1] for d in data['opt_errors']])

max_prog = prog_x[numpy.min(numpy.where(prog_y == 0))]
max_full = full_x[numpy.min(numpy.where(full_y == 0))]
max_opt = opt_x[numpy.min(numpy.where(opt_y == 0))]
max_x = max(max_prog, max_full, max_opt)

fig = plt.figure(figsize=(4,2))
ax = fig.add_subplot(1,1,1)
p1 = ax.plot(prog_x, prog_y, 'o--', color='g', label='Progressive', markersize=2, linewidth=0.5)
p2 = ax.plot(full_x, full_y, 's--', color='r', label='Full Quality', markersize=2, linewidth=0.5)
p3 = ax.plot(opt_x, opt_y, '+--', color='b', label='Original', markersize=2, linewidth=0.5)
p1[0].set_dashes((2,0.7))
p2[0].set_dashes((2,0.7))
p3[0].set_dashes((2,0.7))
#p3 = ax.scatter(x_vals,sorted(orig_fps), color='b', marker='+', s=4, linewidth=0.8, label='Original Flattened')
#p4 = ax.scatter(x_vals,sorted(orig_unflat), color='k', marker='o', s=4, linewidth=0.8, facecolor='None', label='Original')
ax.yaxis.set_major_formatter(MyFormatter())
ax.get_xaxis().tick_bottom()
ax.get_yaxis().tick_left()
ax.set_xlabel('Time (seconds)')
ax.set_ylabel('Perceptual Error (pixels)')
#plt.ylim(0,max(base_fps))
plt.xlim(0, 150) #max_x)
leg = plt.legend(loc=1, prop=prop, markerscale=1.5)
leg.draw_frame(False)
plt.gcf().subplots_adjust(bottom=0.20, left=0.19, right=0.98, top=0.85)
plt.savefig('perceptual_graph.pdf', format='pdf', dpi=150)

#prop = FontProperties(size=7)
#leg = plt.legend(loc=4, prop=prop, markerscale=2.0)
#leg.draw_frame(False)
#llines = leg.get_lines()
#plt.setp(p1, linewidth=0.1)
#plt.setp(p2, linewidth=0.1)
#plt.setp(p3, linewidth=0.1)
#plt.setp(p4, linewidth=0.1)
#
#ax.set_xlabel('Mesh')
#ax.set_ylabel('Frames Per Second')
#plt.gcf().subplots_adjust(bottom=0.24, left=0.14, right=0.95, top=0.98)
#plt.savefig('fps_graph.pdf', format='pdf', dpi=150)
