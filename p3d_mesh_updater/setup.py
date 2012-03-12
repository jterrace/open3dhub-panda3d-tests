import sys
from distutils.core import setup
from distutils.extension import Extension
from Cython.Distutils import build_ext

args = {}

# configure OS dependant compiler settings
# you may need to adjust the paths to match your systems
if sys.platform == 'win32':
    args['include_dirs'] = [r'C:\Panda3D-1.7.0\include']
    args['library_dirs'] = [r'C:\Panda3D-1.7.0\python\libs', r'C:\Panda3D-1.7.0\lib']
    args['extra_compile_args'] = ['/EHsc']
    args['libraries'] = ['libpanda']
elif sys.platform == 'darwin':
    args['include_dirs'] = ['/Developer/Panda3D/include/']
elif sys.platform == 'linux2':
    args['library_dirs'] = [r'/usr/lib/panda3d']
    args['include_dirs'] = ['/usr/include/panda3d/']
    args['libraries'] = ['panda']
else:
    raise OSError("Specify compiler args for your system")

ext_modules = [Extension("cython_impl",
                         sources=["cython_impl.pyx"],
                         language="c++",
                         #extra_compile_args = ["-O3"],
                         **args)]

setup(
  name = 'Panda3D Mesh Updater (cython)',
  cmdclass = {'build_ext': build_ext},
  ext_modules = ext_modules
)
