from panda3d.core import GeomVertexRewriter, GeomVertexWriter, GeomVertexReader
from meshtool.filters.panda_filters.pdae_utils import PM_OP

def update_nodepath(pandaNode, refinements):
    geom = pandaNode.modifyGeom(0)
    
    vertdata = geom.modifyVertexData()
    prim = geom.modifyPrimitive(0)
    indexdata = prim.modifyVertices()
    
    indexrewriter = GeomVertexRewriter(indexdata)
    indexrewriter.setColumn(0)
    nextTriangleIndex = indexdata.getNumRows()
    
    vertwriter = GeomVertexWriter(vertdata, 'vertex')
    numverts = vertdata.getNumRows()
    vertwriter.setRow(numverts)
    normalwriter = GeomVertexWriter(vertdata, 'normal')
    normalwriter.setRow(numverts)
    uvwriter = GeomVertexWriter(vertdata, 'texcoord')
    uvwriter.setRow(numverts)
    
    for refinement in refinements:
        for op_index in range(len(refinement)):
            vals = refinement[op_index]
            op = vals[0]
            if op == PM_OP.TRIANGLE_ADDITION:
                indexrewriter.setRow(nextTriangleIndex)
                nextTriangleIndex += 3
                indexrewriter.addData1i(vals[1])
                indexrewriter.addData1i(vals[2])
                indexrewriter.addData1i(vals[3])
            elif op == PM_OP.INDEX_UPDATE:
                indexrewriter.setRow(vals[1])
                indexrewriter.setData1i(vals[2])
            elif op == PM_OP.VERTEX_ADDITION:
                numverts += 1
                vertwriter.addData3f(vals[1], vals[2], vals[3])
                normalwriter.addData3f(vals[4], vals[5], vals[6])
                uvwriter.addData2f(vals[7], vals[8])
