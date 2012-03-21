import os
import sys
import subprocess
import pickle

CURDIR = os.path.abspath(os.path.dirname(__file__))

PERCEPTUAL_DIFF = os.path.abspath(os.path.expanduser('~/perceptualdiff/perceptualdiff'))

def get_pixel_errors(files, basepath):
    error_vals = []
    blessed_path = os.path.join(basepath, files[-1])
    
    for i, file in enumerate(files):
        timeval = float(file[:-4])
        
        cur_path = os.path.join(basepath, file)
        
        p = subprocess.Popen([PERCEPTUAL_DIFF, '-sum-errors', '-threshold', '1', cur_path, blessed_path], stdout=subprocess.PIPE)
        p.wait()
        retcode = p.returncode
        stdout = p.stdout.read()
        
        error_pixels = 0
        error_sum = 0.0
        
        if retcode != 0:
            lines = stdout.split('\n')
            for line in lines:
                if 'pixels' in line:
                    error_pixels = int(line.split(' ')[0])
                elif 'sum' in line:
                    error_sum = float(line.split(' ')[0])
            assert error_pixels > 0
        
        error_vals.append((timeval, error_pixels, error_sum))
        
        print '%s - %d out of %d' % (basepath, i+1, len(files)), error_pixels, error_sum
    
    return error_vals
        

full_dir = os.path.join(CURDIR, 'ss_small50_full')
full_files = sorted(os.listdir(full_dir))
full_errors = get_pixel_errors(full_files, full_dir)

prog_dir = os.path.join(CURDIR, 'ss_small50_base')
prog_files = sorted(os.listdir(prog_dir))
prog_errors = get_pixel_errors(prog_files, prog_dir)

opt_dir = os.path.join(CURDIR, 'ss_small50_opt')
opt_files = sorted(os.listdir(opt_dir))
opt_errors = get_pixel_errors(opt_files, opt_dir)

unopt_dir = os.path.join(CURDIR, 'ss_small50_unopt')
unopt_files = sorted(os.listdir(unopt_dir))
unopt_errors = get_pixel_errors(unopt_files, unopt_dir)

pickle.dump({'prog_errors': prog_errors,
             'full_errors': full_errors,
             'unopt_errors': unopt_errors,
             'opt_errors': opt_errors},
            open('perceptual_errors.pickle', 'wb'))
