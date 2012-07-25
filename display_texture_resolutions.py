from meshtool.filters.panda_filters.pandacore import getSceneMembers, ensureCameraAt, attachLights
from meshtool.filters.panda_filters.pandacontrols import KeyboardMovement, MouseDrag, MouseScaleZoom, MouseCamera
from direct.gui.DirectGui import DirectButton, DirectSlider, OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import GeomNode, TransparencyAttrib, GeomVertexWriter
from panda3d.core import GeomVertexReader, GeomVertexRewriter, TextNode
from panda3d.core import Mat4, PNMImage, StringStream, Texture
import os
import sys
import numpy
import collada
import tarfile

uiArgs = { 'rolloverSound':None,
           'clickSound':None
        }

class PandaTextureViewer(object):
    
    def __init__(self, mesh_path, progressive_texture_path):

        resolutions = []
        f = tarfile.open(progressive_texture_path)
        for resolution_name in f.getnames():
            toset = {'size': resolution_name[:-4],
                     'contents': f.extractfile(resolution_name).read()}
            texpnm = PNMImage()
            texpnm.read(StringStream(toset['contents']), 'something.jpg')
            newtex = Texture()
            newtex.load(texpnm)
            toset['texture'] = newtex
            resolutions.append(toset)
        
        self.resolutions = resolutions
        def aux_loader(fname):
            return resolutions[0]['contents']
        mesh = collada.Collada(mesh_path, aux_file_loader=aux_loader)
        
        scene_members = getSceneMembers(mesh)
        
        base = ShowBase()
        
        rotateNode = GeomNode("rotater")
        rotatePath = render.attachNewNode(rotateNode)
        matrix = numpy.identity(4)
        if mesh.assetInfo.upaxis == collada.asset.UP_AXIS.X_UP:
            r = collada.scene.RotateTransform(0,1,0,90)
            matrix = r.matrix
        elif mesh.assetInfo.upaxis == collada.asset.UP_AXIS.Y_UP:
            r = collada.scene.RotateTransform(1,0,0,90)
            matrix = r.matrix
        rotatePath.setMat(Mat4(*matrix.T.flatten().tolist()))
        
        geom, renderstate, mat4 = scene_members[0]
        node = GeomNode("primitive")
        node.addGeom(geom)
        if renderstate is not None:
            node.setGeomState(0, renderstate)
        self.geomPath = rotatePath.attachNewNode(node)
        self.geomPath.setMat(mat4)
            
        wrappedNode = ensureCameraAt(self.geomPath, base.camera)
        base.disableMouse()
        attachLights(render)
        render.setShaderAuto()
        render.setTransparency(TransparencyAttrib.MDual, 1)
    
        base.render.analyze()
        KeyboardMovement()
        MouseDrag(wrappedNode)
        MouseScaleZoom(wrappedNode)
        MouseCamera()
        
        num_resolutions = len(resolutions) - 1
        self.slider = DirectSlider(range=(0, num_resolutions),
                                   value=0, pageSize=1,
                                   command=self.sliderMoved, pos=(0, 0, -.9), scale=1)
        for key, val in uiArgs.iteritems():
            self.slider.thumb[key] = val
        
        self.triText = OnscreenText(text="", pos=(-1,0.85), scale = 0.15,
                                    fg=(1, 0.5, 0.5, 1), align=TextNode.ALeft, mayChange=1)
        
        base.run()
        
    def sliderMoved(self):
        sliderVal = int(self.slider['value'])
        #if self.pm_index != sliderVal:
        #    self.movePmTo(sliderVal)
        np = render.find("**/rotater/collada")
        np.setTextureOff(1)
        np.setTexture(self.resolutions[sliderVal]['texture'], 1)
        self.triText.setText('Resolution: %s' % self.resolutions[sliderVal]['size'])

def main():
    mesh = '/home/jterrace/meru/dae_examples/open3dhub/squirrel2/squirrel2.dae'
    prog_textures = '/home/jterrace/meru/dae_examples/open3dhub/squirrel2/squirrel2.tar'
    tex = PandaTextureViewer(mesh, prog_textures)

if __name__ == '__main__':
    main()
