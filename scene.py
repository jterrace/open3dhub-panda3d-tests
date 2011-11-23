import open3dhub
import cPickle
import os

CURDIR = os.path.dirname(__file__)

def filter_non_progressive(models):
    """Filters out models that don't have a progressive version"""
    
    filtered = []
    
    for m in models:
        types = m['metadata']['types']
        if 'progressive' in types:
            filtered.append(m)
    
    return filtered

def filter_zero_progressive(models):
    """Filters out models that have zero triangles in the progressive stream"""
    
    filtered = []
    
    for m in models:
        progressive = m['metadata']['types']['progressive']
        if progressive['progressive_stream_num_triangles'] > 0:
            filtered.append(m)
    
    return filtered

def filter_large_triangles(models):
    """Filters out models that have a base number of triangles that is too large"""
    
    filtered = []
    
    for m in models:
        progressive = m['metadata']['types']['progressive']
        if 'metadata' in progressive and progressive['metadata']['num_triangles'] < 100000:
            filtered.append(m)
    
    return filtered

def filter_no_textures(models):
    """Filters out models that have no textures"""
    
    filtered = []
    
    for m in models:
        optimized = m['metadata']['types']['optimized']
        if 'metadata' in optimized and optimized['metadata']['num_images'] > 0:
            filtered.append(m)
    
    return filtered

def filter_too_complicated(models):
    """Filters out models that have too many draw calls"""
    
    filtered = []
    
    for m in models:
        optimized = m['metadata']['types']['optimized']
        if 'metadata' in optimized and optimized['metadata']['num_draw_calls'] < 50:
            filtered.append(m)
    
    return filtered

BAD_LIST = set(['/ayyyeung/models/tree.dae',
                '/kittyvision/house21.dae',
                '/emily2e/models/apartment_smallLuxury.dae',
                '/echeslack/chess.dae',
                '/kittyvision/apartment1.dae',
                '/zhihongmax/RX_0_Unicorn_Gundam.dae',
                '/emily2e/models/roadblock.dae',
                '/cedar/McLaren_F1_LM.dae'])
def filter_bad_list(models):
    """Filters out models that are known to be bad"""
    
    filtered = []
    for m in models:
        if m['base_path'] not in BAD_LIST:
            filtered.append(m)
    return filtered

def filter_for_demo(models):
    """Filters out models that we don't want to use for the demo"""
    
    models = filter_non_progressive(models)
    models = filter_zero_progressive(models)
    models = filter_large_triangles(models)
    models = filter_no_textures(models)
    models = filter_too_complicated(models)
    models = filter_bad_list(models)
    
    return models

def get_demo_models(force=False):
    """Returns demo models. Loads from a cache unless force is set to True"""
    
    demo_model_file = os.path.join(CURDIR, ".demo-models")
    if not force and os.path.isfile(demo_model_file):
        return cPickle.load(open(demo_model_file, 'r'))
    
    all_cdn_models = open3dhub.get_list(100000)
    demo_models = filter_for_demo(all_cdn_models)
    cPickle.dump(demo_models, open(demo_model_file, 'w'), protocol=cPickle.HIGHEST_PROTOCOL)
    
    return demo_models
