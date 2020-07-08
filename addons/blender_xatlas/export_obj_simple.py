# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

import os

import bpy
import bpy.types
from mathutils import Matrix, Vector, Color
from bpy_extras import io_utils, node_shader_utils

from bpy_extras.wm_utils.progress_report import (
    ProgressReport,
    ProgressReportSubstep,
)


def name_compat(name):
    if name is None:
        return 'None'
    else:
        return name.replace(' ', '_')


def mesh_triangulate(me):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()



def write_file(filepath, objects, scene,
               mainUVChoiceType,
               uvIndex,
               uvName,
               EXPORT_TRI=False,
               EXPORT_EDGES=False,
               EXPORT_SMOOTH_GROUPS=False,
               EXPORT_SMOOTH_GROUPS_BITFLAGS=False,
               EXPORT_NORMALS=False,
               EXPORT_UV=True,
               EXPORT_MTL=True,
               EXPORT_APPLY_MODIFIERS=True,
               EXPORT_APPLY_MODIFIERS_RENDER=False,
               EXPORT_BLEN_OBS=True,
               EXPORT_GROUP_BY_OB=False,
               EXPORT_GROUP_BY_MAT=False,
               EXPORT_KEEP_VERT_ORDER=False,
               EXPORT_POLYGROUPS=False,
               EXPORT_CURVE_AS_NURBS=True,
               EXPORT_GLOBAL_MATRIX=None,
               EXPORT_PATH_MODE='AUTO',
               progress=ProgressReport(),
               ):
    """
    Basic write function. The context and options must be already set
    This can be accessed externaly
    eg.
    write( 'c:\\test\\foobar.obj', Blender.Object.GetSelected() ) # Using default options.
    """
    if EXPORT_GLOBAL_MATRIX is None:
        EXPORT_GLOBAL_MATRIX = Matrix()

    # print('-----------------')
    # print(EXPORT_GLOBAL_MATRIX)

    def veckey3d(v):
        return round(v.x, 4), round(v.y, 4), round(v.z, 4)

    def veckey2d(v):
        return round(v[0], 4), round(v[1], 4)

    def findVertexGroupName(face, vWeightMap):
        """
        Searches the vertexDict to see what groups is assigned to a given face.
        We use a frequency system in order to sort out the name because a given vertex can
        belong to two or more groups at the same time. To find the right name for the face
        we list all the possible vertex group names with their frequency and then sort by
        frequency in descend order. The top element is the one shared by the highest number
        of vertices is the face's group
        """
        weightDict = {}
        for vert_index in face.vertices:
            vWeights = vWeightMap[vert_index]
            for vGroupName, weight in vWeights:
                weightDict[vGroupName] = weightDict.get(vGroupName, 0.0) + weight

        if weightDict:
            return max((weight, vGroupName) for vGroupName, weight in weightDict.items())[1]
        else:
            return '(null)'


    fw = filepath.write


    # Initialize totals, these are updated each object
    totverts = totuvco = totno = 1

    face_vert_index = 1

    copy_set = set()

    # Get all meshes
    for i, ob_main in enumerate(objects):
        # ignore dupli children
        if ob_main.parent and ob_main.parent.instance_type in {'VERTS', 'FACES'}:
            continue

        obs = [(ob_main, ob_main.matrix_world)]

        for ob, ob_mat in obs:
            uv_unique_count = no_unique_count = 0

            ob_for_convert = ob.original

            try:
                me = ob_for_convert.to_mesh()
            except RuntimeError:
                me = None

            if me is None:
                continue

            # _must_ do this before applying transformation, else tessellation may differ
            if EXPORT_TRI:
                # _must_ do this first since it re-allocs arrays
                mesh_triangulate(me)

            me.transform(EXPORT_GLOBAL_MATRIX @ ob_mat)
            # If negative scaling, we have to invert the normals...
            if ob_mat.determinant() < 0.0:
                me.flip_normals()

            if EXPORT_UV:
                faceuv = len(me.uv_layers) > 0
                if faceuv:
                    # uv_layer = me.uv_layers.active.data[:]
                    objUVindex = 0
                    if mainUVChoiceType == "NAME":
                        for i in range(0, len(me.uv_layers)):
                            if me.uv_layers[i].name == uvName:
                                objUVindex = i
                    elif mainUVChoiceType == "INDEX":
                        if uvIndex < len(me.uv_layers):
                            objUVindex = uvIndex

                    if objUVindex < len(me.uv_layers):
                        uv_layer = me.uv_layers[objUVindex].data[:]
                    else:
                        uv_layer = me.uv_layers[0].data[:]
            else:
                faceuv = False

            me_verts = me.vertices[:]

            # Make our own list so it can be sorted to reduce context switching
            face_index_pairs = [(face, index) for index, face in enumerate(me.polygons)]

            if EXPORT_EDGES:
                edges = me.edges
            else:
                edges = []

            if not (len(face_index_pairs) + len(edges) + len(me.vertices)):  # Make sure there is something to write
                # clean up
                ob_for_convert.to_mesh_clear()
                continue  # dont bother with this mesh.

            if EXPORT_NORMALS and face_index_pairs:
                me.calc_normals_split()
                # No need to call me.free_normals_split later, as this mesh is deleted anyway!

            loops = me.loops

            if (EXPORT_SMOOTH_GROUPS or EXPORT_SMOOTH_GROUPS_BITFLAGS) and face_index_pairs:
                smooth_groups, smooth_groups_tot = me.calc_smooth_groups(use_bitflags=EXPORT_SMOOTH_GROUPS_BITFLAGS)
                if smooth_groups_tot <= 1:
                    smooth_groups, smooth_groups_tot = (), 0
            else:
                smooth_groups, smooth_groups_tot = (), 0

            materials = me.materials[:]
            material_names = [m.name if m else None for m in materials]

            # avoid bad index errors
            if not materials:
                materials = [None]
                material_names = [name_compat(None)]

            # Sort by Material, then images
            # so we dont over context switch in the obj file.
            if EXPORT_KEEP_VERT_ORDER:
                pass
            else:
                if len(materials) > 1:
                    if smooth_groups:
                        sort_func = lambda a: (a[0].material_index,
                                                smooth_groups[a[1]] if a[0].use_smooth else False)
                    else:
                        sort_func = lambda a: (a[0].material_index,
                                                a[0].use_smooth)
                else:
                    # no materials
                    if smooth_groups:
                        sort_func = lambda a: smooth_groups[a[1] if a[0].use_smooth else False]
                    else:
                        sort_func = lambda a: a[0].use_smooth

                face_index_pairs.sort(key=sort_func)

                del sort_func

            # Set the default mat to no material and no image.
            contextMat = 0, 0  # Can never be this, so we will label a new material the first chance we get.
            contextSmooth = None  # Will either be true or false,  set bad to force initialization switch.

            if EXPORT_BLEN_OBS or EXPORT_GROUP_BY_OB:
                name1 = ob.name
                name2 = ob.data.name
                # if name1 == name2:
                #     obnamestring = name_compat(name1)
                # else:
                #     obnamestring = '%s_%s' % (name_compat(name1), name_compat(name2))

                #assume all objects have unique names for now
                obnamestring = name_compat(name1)

                if EXPORT_BLEN_OBS:
                    fw('o %s\n' % obnamestring)  # Write Object name
                else:  # if EXPORT_GROUP_BY_OB:
                    fw('g %s\n' % obnamestring)

            # subprogress2.step()

            # Vert
            for v in me_verts:
                fw('v %.6f %.6f %.6f\n' % v.co[:])

            # subprogress2.step()

            # UV
            if faceuv:
                # in case removing some of these dont get defined.
                uv = f_index = uv_index = uv_key = uv_val = uv_ls = None

                uv_face_mapping = [None] * len(face_index_pairs)

                uv_dict = {}
                uv_get = uv_dict.get
                for f, f_index in face_index_pairs:
                    uv_ls = uv_face_mapping[f_index] = []
                    for uv_index, l_index in enumerate(f.loop_indices):
                        uv = uv_layer[l_index].uv
                        # include the vertex index in the key so we don't share UV's between vertices,
                        # allowed by the OBJ spec but can cause issues for other importers, see: T47010.

                        # this works too, shared UV's for all verts
                        #~ uv_key = veckey2d(uv)
                        uv_key = loops[l_index].vertex_index, veckey2d(uv)

                        uv_val = uv_get(uv_key)
                        if uv_val is None:
                            uv_val = uv_dict[uv_key] = uv_unique_count
                            fw('vt %.6f %.6f\n' % uv[:])
                            uv_unique_count += 1
                        uv_ls.append(uv_val)

                del uv_dict, uv, f_index, uv_index, uv_ls, uv_get, uv_key, uv_val
                # Only need uv_unique_count and uv_face_mapping

            # subprogress2.step()

            # NORMAL, Smooth/Non smoothed.
            if EXPORT_NORMALS:
                no_key = no_val = None
                normals_to_idx = {}
                no_get = normals_to_idx.get
                loops_to_normals = [0] * len(loops)
                for f, f_index in face_index_pairs:
                    for l_idx in f.loop_indices:
                        no_key = veckey3d(loops[l_idx].normal)
                        no_val = no_get(no_key)
                        if no_val is None:
                            no_val = normals_to_idx[no_key] = no_unique_count
                            fw('vn %.4f %.4f %.4f\n' % no_key)
                            no_unique_count += 1
                        loops_to_normals[l_idx] = no_val
                del normals_to_idx, no_get, no_key, no_val
            else:
                loops_to_normals = []

            # subprogress2.step()

            # XXX
            if EXPORT_POLYGROUPS:
                # Retrieve the list of vertex groups
                vertGroupNames = ob.vertex_groups.keys()
                if vertGroupNames:
                    currentVGroup = ''
                    # Create a dictionary keyed by face id and listing, for each vertex, the vertex groups it belongs to
                    vgroupsMap = [[] for _i in range(len(me_verts))]
                    for v_idx, v_ls in enumerate(vgroupsMap):
                        v_ls[:] = [(vertGroupNames[g.group], g.weight) for g in me_verts[v_idx].groups]

            for f, f_index in face_index_pairs:
                f_smooth = f.use_smooth
                if f_smooth and smooth_groups:
                    f_smooth = smooth_groups[f_index]
                f_mat = min(f.material_index, len(materials) - 1)

                # MAKE KEY
                key = material_names[f_mat], None  # No image, use None instead.

                # Write the vertex group
                if EXPORT_POLYGROUPS:
                    if vertGroupNames:
                        # find what vertext group the face belongs to
                        vgroup_of_face = findVertexGroupName(f, vgroupsMap)
                        if vgroup_of_face != currentVGroup:
                            currentVGroup = vgroup_of_face
                            fw('g %s\n' % vgroup_of_face)

                # CHECK FOR CONTEXT SWITCH
                if key == contextMat:
                    pass  # Context already switched, dont do anything
                

                contextMat = key
                if f_smooth != contextSmooth:
                    if f_smooth:  # on now off
                        if smooth_groups:
                            f_smooth = smooth_groups[f_index]
                            fw('s %d\n' % f_smooth)
                        else:
                            fw('s 1\n')
                    else:  # was off now on
                        fw('s off\n')
                    contextSmooth = f_smooth

                f_v = [(vi, me_verts[v_idx], l_idx)
                        for vi, (v_idx, l_idx) in enumerate(zip(f.vertices, f.loop_indices))]

                fw('f')
                if faceuv:
                    if EXPORT_NORMALS:
                        for vi, v, li in f_v:
                            fw(" %d/%d/%d" % (totverts + v.index,
                                                totuvco + uv_face_mapping[f_index][vi],
                                                totno + loops_to_normals[li],
                                                ))  # vert, uv, normal
                    else:  # No Normals
                        for vi, v, li in f_v:
                            fw(" %d/%d" % (totverts + v.index,
                                            totuvco + uv_face_mapping[f_index][vi],
                                            ))  # vert, uv

                    face_vert_index += len(f_v)

                else:  # No UV's
                    if EXPORT_NORMALS:
                        for vi, v, li in f_v:
                            fw(" %d//%d" % (totverts + v.index, totno + loops_to_normals[li]))
                    else:  # No Normals
                        for vi, v, li in f_v:
                            fw(" %d" % (totverts + v.index))

                fw('\n')

            # subprogress2.step()

            # Write edges.
            if EXPORT_EDGES:
                for ed in edges:
                    if ed.is_loose:
                        fw('l %d %d\n' % (totverts + ed.vertices[0], totverts + ed.vertices[1]))

            # Make the indices global rather then per mesh
            totverts += len(me_verts)
            totuvco += uv_unique_count
            totno += no_unique_count

            # clean up
            ob_for_convert.to_mesh_clear()

        #end forloop

    #print(filepath.getvalue())



def _write(
           context,
           filepath,
           mainUVChoiceType,
           uvIndex,
           uvName,
           EXPORT_TRI,  # ok
           EXPORT_EDGES,
           EXPORT_SMOOTH_GROUPS,
           EXPORT_SMOOTH_GROUPS_BITFLAGS,
           EXPORT_NORMALS,  # ok
           EXPORT_UV,  # ok
           EXPORT_MTL,
           EXPORT_APPLY_MODIFIERS,  # ok
           EXPORT_APPLY_MODIFIERS_RENDER,  # ok
           EXPORT_BLEN_OBS,
           EXPORT_GROUP_BY_OB,
           EXPORT_GROUP_BY_MAT,
           EXPORT_KEEP_VERT_ORDER,
           EXPORT_POLYGROUPS,
           EXPORT_CURVE_AS_NURBS,
           EXPORT_SEL_ONLY,  # ok
           EXPORT_ANIMATION,
           EXPORT_GLOBAL_MATRIX,
           EXPORT_PATH_MODE,  # Not used
           ):

        scene = context.scene

        # Exit edit mode before exporting, so current object states are exported properly.
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        #Only use selected objs
        #Let something further up manage selection
        objects = context.selected_objects

        write_file(
            filepath,
            objects,
            scene,
            mainUVChoiceType,
            uvIndex,
            uvName,
            EXPORT_TRI,
            EXPORT_EDGES,
            EXPORT_SMOOTH_GROUPS,
            EXPORT_SMOOTH_GROUPS_BITFLAGS,
            EXPORT_NORMALS,
            EXPORT_UV,
            EXPORT_MTL,
            EXPORT_APPLY_MODIFIERS,
            EXPORT_APPLY_MODIFIERS_RENDER,
            EXPORT_BLEN_OBS,
            EXPORT_GROUP_BY_OB,
            EXPORT_GROUP_BY_MAT,
            EXPORT_KEEP_VERT_ORDER,
            EXPORT_POLYGROUPS,
            EXPORT_CURVE_AS_NURBS,
            EXPORT_GLOBAL_MATRIX,
            EXPORT_PATH_MODE,
            )


"""
Currently the exporter lacks these features:
* multiple scene export (only active scene is written)
* particles
"""

def save(
        context,
        filepath,
        mainUVChoiceType,
        uvIndex,
        uvName,
        *,
        use_triangles=False,
        use_edges=True,
        use_normals=False,
        use_smooth_groups=False,
        use_smooth_groups_bitflags=False,
        use_uvs=True,
        use_materials=True,
        use_mesh_modifiers=True,
        use_mesh_modifiers_render=False,
        use_blen_objects=True,
        group_by_object=False,
        group_by_material=False,
        keep_vertex_order=False,
        use_vertex_groups=False,
        use_nurbs=True,
        use_selection=True,
        use_animation=False,
        global_matrix=None,
        path_mode='AUTO'
        ):

    _write(context,filepath,
        mainUVChoiceType,
        uvIndex,
        uvName,
        EXPORT_TRI=use_triangles,
        EXPORT_EDGES=use_edges,
        EXPORT_SMOOTH_GROUPS=use_smooth_groups,
        EXPORT_SMOOTH_GROUPS_BITFLAGS=use_smooth_groups_bitflags,
        EXPORT_NORMALS=use_normals,
        EXPORT_UV=use_uvs,
        EXPORT_MTL=use_materials,
        EXPORT_APPLY_MODIFIERS=use_mesh_modifiers,
        EXPORT_APPLY_MODIFIERS_RENDER=use_mesh_modifiers_render,
        EXPORT_BLEN_OBS=use_blen_objects,
        EXPORT_GROUP_BY_OB=group_by_object,
        EXPORT_GROUP_BY_MAT=group_by_material,
        EXPORT_KEEP_VERT_ORDER=keep_vertex_order,
        EXPORT_POLYGROUPS=use_vertex_groups,
        EXPORT_CURVE_AS_NURBS=use_nurbs,
        EXPORT_SEL_ONLY=use_selection,
        EXPORT_ANIMATION=use_animation,
        EXPORT_GLOBAL_MATRIX=global_matrix,
        EXPORT_PATH_MODE=path_mode,
        )

    return {'FINISHED'}