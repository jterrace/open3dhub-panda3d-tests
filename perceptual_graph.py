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
rc('font', family='sans-serif')

class MyFormatter(Formatter):
    def __call__(self, val, idx):
        #return ("%g" % val).lstrip('0') or '0'
        return "%dK" % (val / 1000.0)

prop = FontProperties(size=7)
data = pickle.load(open('pix_sum_big50.pickle', 'rb'))
#data = pickle.load(open('perceptual_errors.pickle', 'rb'))

prog_x = numpy.array([d[0] for d in data['prog_errors']], dtype=float)
prog_y = numpy.array([d[1] for d in data['prog_errors']], dtype=float)
#prog_y /= numpy.max(prog_y)

full_x = numpy.array([d[0] for d in data['full_errors']], dtype=float)
full_y = numpy.array([d[2] for d in data['full_errors']], dtype=float)
full_y /= numpy.max(full_y)

opt_x = numpy.array([d[0] for d in data['opt_errors']], dtype=float)
opt_y = numpy.array([d[2] for d in data['opt_errors']], dtype=float)
opt_y /= numpy.max(opt_y)

unopt_x = numpy.array([d[0] for d in data['unopt_errors']], dtype=float)
unopt_y = numpy.array([d[2] for d in data['unopt_errors']], dtype=float)
unopt_y /= numpy.max(unopt_y)

max_prog = prog_x[numpy.min(numpy.where(prog_y == 0))]
max_full = full_x[numpy.min(numpy.where(full_y == 0))]
max_opt = opt_x[numpy.min(numpy.where(opt_y == 0))]
max_unopt = unopt_x[numpy.min(numpy.where(unopt_y == 0))]
max_x = max(max_prog, max_full, max_opt, max_unopt)

fig = plt.figure(figsize=(5.5,4.25))
ax = fig.add_subplot(1,1,1)
p1 = ax.plot(prog_x, prog_y, 'o--', color='g', label='Progressive', markersize=3, linewidth=1)
#p2 = ax.plot(full_x, full_y, 's--', color='r', label='Full Quality', markersize=3, linewidth=1)
#p3 = ax.plot(opt_x, opt_y, '+--', color='b', label='Optimized', markersize=3, linewidth=1)
#p4 = ax.plot(unopt_x, unopt_y, 'x--', color='k', label='Original', markersize=3, linewidth=1)
p1[0].set_dashes((2,0.7))
#p2[0].set_dashes((2,0.7))
#p3[0].set_dashes((2,0.7))
#p4[0].set_dashes((2,0.7))
#p3 = ax.scatter(x_vals,sorted(orig_fps), color='b', marker='+', s=4, linewidth=0.8, label='Original Flattened')
#p4 = ax.scatter(x_vals,sorted(orig_unflat), color='k', marker='o', s=4, linewidth=0.8, facecolor='None', label='Original')
ax.yaxis.set_major_formatter(MyFormatter())
ax.get_xaxis().tick_bottom()
ax.get_yaxis().tick_left()
ax.set_xlabel('Time (seconds)')
ax.set_ylabel('Perceptual Error (pixels)')
#plt.title('50 Big Meshes')
plt.ylim(0,125000)
plt.xlim(0, 200)
#leg = plt.legend(loc=1, prop=prop, markerscale=1.5)
#leg.draw_frame(False)
plt.gcf().subplots_adjust(bottom=0.10, left=0.14, right=0.97, top=0.97)
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
