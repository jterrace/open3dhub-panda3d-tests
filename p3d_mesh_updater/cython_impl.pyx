from libcpp cimport bool

cdef char* CONST_vertex = "vertex"
cdef char* CONST_normal = "normal"
cdef char* CONST_texcoord = "texcoord"

cdef enum PM_OP:
    INDEX_UPDATE = 1
    TRIANGLE_ADDITION = 2
    VERTEX_ADDITION = 3

cdef extern from "py_panda.h":
    cdef struct Dtool_PyInstDef:
        void* _ptr_to_object

cdef void* get_ptr(object o):
    return (<Dtool_PyInstDef*>o)._ptr_to_object

cdef extern from "<string>" namespace "std":
    cdef cppclass string:
        string()
        string(char *)
        char* c_str()
        bint operator==(string&)
        bint operator==(char*)

cdef extern from "geomVertexData.h":
    cdef cppclass GeomVertexData:
        int get_num_rows()
cdef extern from "geomVertexArrayData.h":
    cdef cppclass GeomVertexArrayData:
        int get_num_rows()
cdef extern from "thread.h":
    cdef cppclass Thread:
        pass
cdef extern from "geomVertexWriter.h":
    cdef cppclass GeomVertexWriter:
        GeomVertexWriter(GeomVertexData *vertex_data, string name)
        GeomVertexWriter(GeomVertexArrayData* arr_data)
        bool set_column(int column)
        void set_row(int column)
        void add_data1i(int data)
        void add_data3f(float x, float y, float z)
        void add_data2f(float x, float y)
        void set_data1i(int data)
cdef extern from "geomVertexRewriter.h":
    cdef cppclass GeomVertexRewriter:
        GeomVertexRewriter(GeomVertexArrayData*)
        bool set_column(int column)
        void set_row(int column)
        void set_data1i(int data)
        void add_data1i(int data)
cdef extern from "geomPrimitive.h":
    cdef cppclass GeomPrimitive:
        GeomVertexArrayData* modify_vertices(int num_vertices)
cdef extern from "geom.h":
    cdef cppclass Geom:
        GeomVertexData* modify_vertex_data()
        GeomPrimitive* modify_primitive(int i)
cdef extern from "pandaNode.h":
    cdef cppclass PandaNode:
        pass
cdef extern from "geomNode.h":
    cdef cppclass GeomNode(PandaNode):
        Geom* modify_geom(int n)
cdef extern from "nodePath.h":
    cdef cppclass NodePath:
        PandaNode* node()
        bool is_empty()

def update_nodepath(pandaNode, list refinements):

    cdef GeomNode* gnode = <GeomNode*>get_ptr(pandaNode)
    cdef Geom* geom = gnode.modify_geom(0)
    cdef GeomVertexData* vertdata = geom.modify_vertex_data()
    cdef GeomPrimitive* prim = geom.modify_primitive(0)
    cdef GeomVertexArrayData* indexdata = prim.modify_vertices(-1)

    cdef GeomVertexWriter* indexwriter = new GeomVertexWriter(indexdata)
    indexwriter.set_column(0)
    cdef int nextTriangleIndex = indexdata.get_num_rows()

    cdef GeomVertexWriter* vertwriter = new GeomVertexWriter(vertdata, string(CONST_vertex))
    cdef int numverts = vertdata.get_num_rows()
    vertwriter.set_row(numverts)
    cdef GeomVertexWriter* normalwriter = new GeomVertexWriter(vertdata, string(CONST_normal))
    normalwriter.set_row(numverts)
    cdef GeomVertexWriter* uvwriter = new GeomVertexWriter(vertdata, string(CONST_texcoord))
    uvwriter.set_row(numverts)

    cdef int op_index
    cdef int op
    cdef tuple vals
    for refinement in refinements:
        for op_index in range(len(refinement)):
            vals = refinement[op_index]
            op = vals[0]
            if op == TRIANGLE_ADDITION:
                indexwriter.set_row(nextTriangleIndex)
                nextTriangleIndex += 3
                indexwriter.add_data1i(vals[1])
                indexwriter.add_data1i(vals[2])
                indexwriter.add_data1i(vals[3])
            elif op == INDEX_UPDATE:
                indexwriter.set_row(vals[1])
                indexwriter.set_data1i(vals[2])
            elif op == VERTEX_ADDITION:
                numverts += 1
                vertwriter.add_data3f(vals[1], vals[2], vals[3])
                normalwriter.add_data3f(vals[4], vals[5], vals[6])
                uvwriter.add_data2f(vals[7], vals[8])

    del uvwriter
    del normalwriter
    del vertwriter
    del indexwriter
    