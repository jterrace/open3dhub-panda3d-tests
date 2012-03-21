import argparse
import math
import random
import pickle
import posixpath
import os

import scene
import open3dhub
import load_scheduler

BIG_ONLY = False
SMALL_ONLY = False

def gen_x_y(num_models):
    #X_SIZE = 3
    #Y_SIZE = int(math.ceil(float(num_models) / X_SIZE))
    #for x in range(X_SIZE):
    #    for y in range(Y_SIZE):
    #        print x,y
    #        yield ((float(x + 0.5 + random.uniform(-0.2,0.2)) / X_SIZE) * 16000 - 8000,
    #               (float(y + 0.5 + random.uniform(-0.2,0.2))) * -8000 + 8000)
    
    y = 0
    x_size = 3.0
    while True:
        for x in range(int(round(x_size))):
            yield ((float(x + 0.5 + random.uniform(-0.2,0.2)) / x_size) * (x_size * 5000) - (x_size * 2500),
                   (float(y + 0.5 + random.uniform(-0.2,0.2))) * -8000 + 8000)
        x_size += 0.5
        y += 1

def get_random_models(num_models):
    progressive_models = scene.get_progressive_models()
    print 'Loaded', len(progressive_models), 'models'
    small_models = scene.filter_non_small(progressive_models)
    big_models = scene.filter_non_big(progressive_models)
    print len(big_models), 'big models', len(small_models), 'small models'

    if BIG_ONLY:
        print 'Using big models only'
        progressive_models = big_models
    if SMALL_ONLY:
        print 'Using small models only'
        progressive_models = small_models

    to_choose = range(len(progressive_models))
    chosen = []
    xygen = gen_x_y(num_models)
    while len(chosen) < num_models:
        rand_index = random.randrange(len(to_choose))
        chosen_index = to_choose.pop(rand_index)
        
        model_json = progressive_models[chosen_index]
        types = model_json['metadata']['types']
        for type_name, type_data in types.iteritems():
            type_data['subfile_hashes'] = []
            for subfile in type_data['subfiles']:
                splitpath = subfile.split('/')
                basename = splitpath[-2]
                subfile_path = posixpath.normpath(posixpath.join(model_json['base_path'], type_name, model_json['version_num'], basename))
                subfile_hash = open3dhub.get_subfile_hash(subfile_path)
                type_data['subfile_hashes'].append(subfile_hash)
        
        x, y = next(xygen)
        model = load_scheduler.Model(model_json = model_json,
                            model_type = 'progressive',
                            x = x,
                            y = y,
                            z = 0,
                            scale = random.uniform(0.5, 6.0))
        
        chosen.append(model)
    
    return chosen

def main():   
    parser = argparse.ArgumentParser(description='Generate a random scene file from open3dhub models')

    parser.add_argument('num_models', help='Number of models to use', type=int)
    parser.add_argument('scene_out', metavar='scene.out', help='File to save the scene to', type=argparse.FileType('w'))
    parser.add_argument('--seed', required=False, help='Seed for random number generator', type=str)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--small-only', action='store_true', default=False)
    group.add_argument('--big-only', action='store_true', default=False)
    
    args = parser.parse_args()
    
    global BIG_ONLY, SMALL_ONLY
    if args.big_only:
        BIG_ONLY = True
    if args.small_only:
        SMALL_ONLY = True
    
    if args.seed is not None:
        random.seed(args.seed)
    
    models = get_random_models(args.num_models)
    
    json_items = [model.model_json for model in models]
    print 'Obtaining hash sizes'
    hash_sizes = open3dhub.get_hash_sizes(json_items)
    print 'Got', len(hash_sizes), 'hash sizes'
    
    print 'Saving', len(models), 'scene members to file', args.scene_out
    pickle.dump({'models': models, 'sizes': hash_sizes}, args.scene_out)

if __name__ == '__main__':
    main()
