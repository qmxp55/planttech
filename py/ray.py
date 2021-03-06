
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import open3d as o3d
import os, sys, glob
import laspy as lp
from scipy.stats import chisquare
from time import process_time

import pyrr 
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import itertools
from tqdm import tqdm

import figures
import loads
import lad

__author__ = 'Omar A. Ruiz Macias'
__copyright__ = 'Copyright 2021, PLANTTECH'
__version__ = '0.1.0'
__maintainer__ = 'Omar A. Ruiz Macias'
__email__ = 'omar.ruiz.macias@gmail.com'
__status__ = 'Dev'

# Global
basedir = os.path.dirname(os.getcwd())
_py = os.path.join(basedir, 'py')
_data = os.path.join(basedir, 'data')
_images = os.path.join(basedir, 'images')

def cuboid_data2(o, size=(1,1,1)):
    X = [[[0, 1, 0], [0, 0, 0], [1, 0, 0], [1, 1, 0]],
         [[0, 0, 0], [0, 0, 1], [1, 0, 1], [1, 0, 0]],
         [[1, 0, 1], [1, 0, 0], [1, 1, 0], [1, 1, 1]],
         [[0, 0, 1], [0, 0, 0], [0, 1, 0], [0, 1, 1]],
         [[0, 1, 0], [0, 1, 1], [1, 1, 1], [1, 1, 0]],
         [[0, 1, 1], [0, 0, 1], [1, 0, 1], [1, 1, 1]]]
    X = np.array(X).astype(float)
    for i in range(3):
        X[:,:,i] *= size[i]
    X += np.array(o)
    return X

def plotCubeAt2(positions,sizes=None,colors=None, **kwargs):
    if not isinstance(colors,(list,np.ndarray)): 
        colors=["C0"]*len(positions)
    if not isinstance(sizes,(list,np.ndarray)): sizes=[(1,1,1)]*len(positions)
    g = []
    # colors = np.empty(axes + [4], dtype=np.float32)
    alpha = 0.2
    # colors[:] = [1, 0, 0, alpha]  # red
    for p,s,c in zip(positions,sizes,colors):
        g.append( cuboid_data2(p, size=s) )
    return Poly3DCollection(np.concatenate(g),  
                            facecolors=(colors), edgecolor="k")

def split_BB(box, voxel_size):

    # minBB, maxBB = box
    # minBB = np.array(minBB)
    # maxBB = np.array(maxBB)

    pr_invoxels = (np.array(box[1]) - np.array(box[0]))/voxel_size
    pr_invoxels = np.round(pr_invoxels, 4)
    mid_distances = np.floor_divide(pr_invoxels,2)
    mark = mid_distances.sum()

    # check that dimensions of plant region are  multiples of the voxel size
    if np.all(np.mod(pr_invoxels, 1) != 0):
        raise ValueError('Voxel size %.3f is not a multiple of the plant region dimensions' %(voxel_size))


    if mark == 0:
        return [box]#, mid_distances.sum()

    else:

        # Split each side of plant region by 2 but get integers only
        # mid_distances = np.floor_divide(pr_invoxels,2)
        xi, yi, zi = np.transpose([[0,0,0], mid_distances.tolist()])
        xf, yf, zf = np.transpose([mid_distances.tolist(), pr_invoxels.tolist()])

        minBB_ = list(itertools.product(xi, yi, zi))
        maxBB_ = list(itertools.product(xf, yf, zf))

        boxes = []
        for i in range(len(minBB_)):

            A = np.array(box[0]) + np.array(minBB_[i]) * voxel_size
            B = np.array(box[0]) + np.array(maxBB_[i]) * voxel_size
            boxes.append(pyrr.aabb.create_from_bounds(A, B).tolist())

        return boxes#, mark

def get_matPR(vox, voxel_size):
    '''
    Get 3D-boolean-array of plant region dimmensions
    '''

    # Create voxel of plant region
    width, height, depth = vox.get_max_bound() - vox.get_min_bound()
    # print(width, height, depth)
    voxs = o3d.geometry.VoxelGrid.create_dense(origin=vox.origin, color=np.array([0,0,1]), voxel_size=voxel_size, width=width, height=height, depth=depth)

    # get voxel grid indexes for points and beams voxels
    voxp_idx = lad.get_voxels(vox)

    # Get solid voxel grid indexes
    voxs_idx = lad.get_voxels(voxs)

    # get i,j,k max and min
    vdict = lad.idx_bounds(voxs_idx, False)
    # ijk_bounds = np.array(list(vdict.values())).reshape(1,6)[0]

    # create 3D boolean matrix of i,j,k size
    m3s = np.zeros(np.array(vdict['ijk_max'])+1, dtype=bool)
    # print(m3s.shape)

    # fill 3D matrix with True if voxel exist
    # m3p = m3s.copy()
    # for (i,j,k) in voxp_idx:
        
    #     m3p[i][j][k] = True

    return m3s, voxs, voxp_idx


def intercept(ray, boxPR, voxel_size):

    boxes_reached = split_BB(boxPR, voxel_size)

    marks = 99
    count = 0

    while marks > 0:

        boxes = [box for box in boxes_reached if pyrr.geometric_tests.ray_intersect_aabb(ray, box) is not None]

        boxes_reached = []
        marks = 0

        boxes_ = [split_BB(box, voxel_size) for box in boxes]
        marks = [len(i) - 1 for i in boxes_]
        marks = np.array(marks).sum()
        boxes_reached =  [j for i in boxes_ for j in i]

        count += 1

    return boxes_reached

def get_all_AABB(boxPR, voxel_size, stop):

    boxes_reached = split_BB(boxPR, voxel_size)

    marks = 99
    count = 0

    while marks > 0:

        boxes = [box for box in boxes_reached]
        if len(boxes) == 8**stop:
            boxes_stop = boxes

        boxes_reached = []
        marks = 0

        boxes_ = [split_BB(box, voxel_size) for box in boxes]
        marks = [len(i) - 1 for i in boxes_]
        marks = np.array(marks).sum()
        boxes_reached =  [j for i in boxes_ for j in i]
        
        # print('marks: ', marks)

        count += 1

    return np.array(boxes_reached), np.array(boxes_stop)

def get_all_voxels_in_stop(AABBc, boxes_stop):
    '''
    Find the ultimate voxels (the smallest voxels) within the requested
    stop voxels that are bigger.
    '''

    X, Y, Z = np.array(AABBc).T
    boxes_stop_idx = np.full(len(X), -1)
    boxes_stop_dict = {}

    # fig = plt.figure()
    # ax = fig.add_subplot(111, projection='3d')

    # positions = [(minBB[0], minBB[1], minBB[2])]
    # sizes = [(width, height, depth)]
    # pc = rayt.plotCubeAt2(positions,sizes,colors=[1,0,0,0.2], edgecolor="k")
    # ax.add_collection3d(pc)

    # ax.set_xlim([-18,18])
    # ax.set_ylim([-18,18])
    # ax.set_zlim([0,20])

    for num, box in enumerate(boxes_stop):

        boxes_stop_dict[num] = pyrr.aabb.centre_point(box).tolist()
        keep = np.ones(len(AABBc), dtype=bool)

        xi, yi, zi = np.array(box[0])
        xf, yf, zf = np.array(box[1])
        
        keep &= (X > xi) & (X < xf)
        keep &= (Y > yi) & (Y < yf)
        keep &= (Z > zi) & (Z < zf)

        # print(keep.sum())

        boxes_stop_idx[keep] = num

        # if num < 2:
        #     ax.scatter3D(X[keep], Y[keep], Z[keep], s=20)

    # keep = (boxes_stop_idx == -1)
    # ax.scatter3D(X[keep], Y[keep], Z[keep], c='k', s=20)

    return boxes_stop_idx, boxes_stop_dict

def build_matrixes(m3s, boxes_stop_idx, boxes_reached, AABB2vgidx):

    m3AABB = np.empty_like(m3s, dtype=object)
    m3stop = np.zeros_like(m3s, dtype=int)

    keep = (boxes_stop_idx != -1)
    boxes_stop_idx = boxes_stop_idx[keep]
    boxes_reached = boxes_reached[keep]
    idx = np.array(AABB2vgidx(boxes_reached))

    for num,(i,j,k) in enumerate(idx):

        m3AABB[i][j][k] = boxes_reached[num]
        m3stop[i][j][k] = np.array(boxes_stop_idx[num])

    return m3AABB, m3stop

def reached_in_stop(boxes_stop_dict, boxes_reached, m3stop):

    key_list = list(boxes_stop_dict.keys())
    val_list = list(boxes_stop_dict.values())

    AABBc_ = [pyrr.aabb.centre_point(box).tolist() for box in boxes_reached]
    idxs = [key_list[val_list.index(i)] for i in AABBc_]

    m3_ = np.zeros_like(m3stop, dtype=bool)

    for idx in idxs:
        # print(idx)
        m3_ |= (m3stop == idx)
    
    return m3_

def prAABB(points, voxel_size):

    # get bounding box of plant region
    pcd = loads.points2pcd(points)
    voxPR = o3d.geometry.VoxelGrid.create_from_point_cloud(pcd, voxel_size=voxel_size)
    maxBB = voxPR.get_max_bound()
    minBB = voxPR.get_min_bound()

    return voxPR, minBB, maxBB


def mainOLD(mockname, voxel_size, downsample=None, sample=None, stop=None, show=False):

    mockdir = os.path.join(_data, mockname)
    spos = os.path.join(mockdir, 'scanner_pos.txt')
    rawdata_files = glob.glob(os.path.join(mockdir, 's*.npy'))

    scan = lad.laod_scan_pos(spos)
    id = [i.decode("utf-8") for i in scan['scan']]

    # get bounding box of plant region
    segtrees_dir = os.path.join(mockdir, 'toy_trees')
    segtrees_files = glob.glob(os.path.join(segtrees_dir, 'tree_*.npy'))
    tree = np.load(segtrees_files[0])
    treename = segtrees_files[0].split('/')[-1].split('.')[0]
    pointsPR = tree.T[5:8].T
    pcd = lad.points2pcd(pointsPR)
    voxPR = o3d.geometry.VoxelGrid.create_from_point_cloud(pcd, voxel_size=voxel_size)
    maxBB = voxPR.get_max_bound()
    minBB = voxPR.get_min_bound()
    width, height, depth = maxBB - minBB

    outdir = os.path.join(segtrees_dir, 'm3s_%s_%s.npy' %(treename, str(voxel_size)))
    outdir_count = os.path.join(segtrees_dir, 'm3count_%s_%s.npy' %(treename, str(voxel_size)))

    # Get 3D-boolean-array of plant region dimmensions and solid voxel
    m3s, voxs = get_matPR(vox=voxPR, voxel_size=voxel_size)
    totvox = (~m3s).sum()
    AABB2vgidx = lambda boxes: [voxs.get_voxel(pyrr.aabb.centre_point(box)).tolist() for box in boxes]
    # create BB for ray interceptio
    boxPR = pyrr.aabb.create_from_bounds(minBB, maxBB)
    m3count = np.full_like(m3s, 0, dtype=int)

    # fixed quantities
    if stop is not None:
        boxes_reached, boxes_stop = get_all_AABB(boxPR, voxel_size, stop=stop)
        AABBc = [pyrr.aabb.centre_point(box).tolist() for box in boxes_reached]
        boxes_stop_idx, boxes_stop_dict = get_all_voxels_in_stop(AABBc, boxes_stop)
        m3AABB, m3stop = build_matrixes(m3s, boxes_stop_idx, boxes_reached, AABB2vgidx)
        print('Stop quantities done')
    # plot bounding box

    if show:

        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        positions = [(minBB[0], minBB[1], minBB[2])]
        sizes = [(width, height, depth)]
        pc = plotCubeAt2(positions,sizes,colors=[1,0,0,0.2], edgecolor="k")
        ax.add_collection3d(pc)

        ax.set_xlim([-18,18])
        ax.set_ylim([-18,18])
        ax.set_zlim([0,20])
    else:
        ax = None

    for file in rawdata_files:

        filename = file.split('/')[-1]
        print('FILE: \t', filename)

        df = np.load(file)
        # print(len(df))
        print('size BPC: \t', len(df))

        if sample is not None:
            keep = np.random.randint(0, len(df), sample)
            df = df[keep]

        
        if downsample is not None:
            idxlpc = np.random.randint(0, len(df), int(len(df) * downsample))
            df = df[idxlpc]

        print('size new BPC: \t', len(df))

        points = df.T[5:8].T
        keep = np.array(id) == filename[:3]
        _, sx, sy, sz = scan[keep][0]
        # sensor coordinates
        p2 = [sx, sy, sz]

        if show:
            ax.scatter3D(sx, sy, sz, c='r', s=20, marker='*')

        for p1 in tqdm(points):

            line = pyrr.line.create_from_points(p1, p2, dtype=None)
            ray = pyrr.ray.create_from_line(line)

            res = pyrr.geometric_tests.ray_intersect_aabb(ray, boxPR)

            if res is not None:

                if stop is not None:

                    boxes_reached = intercept2(ray, boxPR, voxel_size, stop)
                    m3_ = reached_in_stop(boxes_stop_dict, boxes_reached, m3stop)
                    keep = (m3_) & (~m3s)
                    # print('voxels found', m3_.sum())
                    # print('voxels occupied', m3s.sum())
                    # print('voxels to test: \t %i' %(keep.sum()))
                    if keep.sum() == 0: continue
                    boxes = [box for box in m3AABB[keep] if pyrr.geometric_tests.ray_intersect_aabb(ray, box) is not None]
                    # print('voxels hitted', len(boxes))
                    if len(boxes) == 0: continue

                    # if len(boxes_reached) == 0: continue
                    # print(np.array(boxes_reached).shape)
                    # Update 3D-boolean-array

                else:
                    
                    boxes = intercept2(ray, boxPR, voxel_size, stop)

                idx = np.array(AABB2vgidx(boxes))
                m3s[idx.T[0], idx.T[1], idx.T[2]] = True
                m3count[idx.T[0], idx.T[1], idx.T[2]] += 1

                if show:

                    for box in boxes:

                        minBB, maxBB = box
                        minBB = np.array(minBB)
                        maxBB = np.array(maxBB)
                        width, height, depth = maxBB - minBB
                        # plot bounding box
                        positions = [(minBB[0], minBB[1], minBB[2])]
                        sizes = [(width, height, depth)]
                        pc = plotCubeAt2(positions,sizes,colors=[0,1,0,0.4], edgecolor="k")
                        ax.add_collection3d(pc)

                    ax.plot(*line.T.tolist())
                    ax.scatter3D(*p1, c='g', s=10)
                    ax.scatter3D(*res, c='k', s=10)
    
    if show: plt.show()

    print('tot vox: \t %i' %(totvox))
    print('voxels hitted: \t %i' %(m3s.sum()))
    print('Percentage of voxels hitted by beam: %.2f' %(m3s.sum()/totvox))

    np.save(outdir, m3s)
    np.save(outdir_count, m3count)

    return m3s, m3count

def PCdensity(mockname, voxel_size):

    mockdir = os.path.join(_data, mockname)
    spos = os.path.join(mockdir, 'scanner_pos.txt')
    rawdata_files = glob.glob(os.path.join(mockdir, 's*.npy'))
    scan = lad.laod_scan_pos(spos)
    id = [i.decode("utf-8") for i in scan['scan']]

    # get bounding box of plant region
    segtrees_dir = os.path.join(mockdir, 'toy_trees')
    segtrees_files = glob.glob(os.path.join(segtrees_dir, 'tree_*.npy'))
    tree = np.load(segtrees_files[0])
    pointsPR = tree.T[5:8].T
    pcd = lad.points2pcd(pointsPR)
    voxPR = o3d.geometry.VoxelGrid.create_from_point_cloud(pcd, voxel_size=voxel_size)
    maxBB = voxPR.get_max_bound()
    minBB = voxPR.get_min_bound()
    width, height, depth = maxBB - minBB
    volume = width * height * depth
    print('PR volume: \t', volume)

    boxPR = pyrr.aabb.create_from_bounds(minBB, maxBB)

    Nipr = 0
    Nopr = 0
    Nlpc = len(tree)

    for file in rawdata_files:

        filename = file.split('/')[-1]
        df = np.load(file)

        points = df.T[5:8].T
        keep = np.array(id) == filename[:3]
        _, sx, sy, sz = scan[keep][0]
        # sensor coordinates
        p2 = [sx, sy, sz]

        for p1 in tqdm(points):

            line = pyrr.line.create_from_points(p1, p2, dtype=None)
            ray = pyrr.ray.create_from_line(line)

            res = pyrr.geometric_tests.ray_intersect_aabb(ray, boxPR)

            if res is not None:
                Nipr += 1
            else:
                Nopr += 1

    Npt = Nipr - Nlpc
    print('# colide with PR: \t', Nipr)
    print('# Dont colide with PR: \t', Nopr)
    print('# colide with leaves: \t', Nlpc)
    print('# pass trhough PR: \t', Npt)

    return Nipr, Nopr, Nlpc, Npt, volume

def main(points, sensors, pointsPR, voxel_size, resdir, treename, show=False):

    voxPR, minBB, maxBB = prAABB(pointsPR, voxel_size)
    width, height, depth = maxBB - minBB 

    # Get 3D-boolean-array of plant region dimmensions and solid voxel
    m3s, voxs, voxp_idx = get_matPR(vox=voxPR, voxel_size=voxel_size)
    m3s2 = m3s.copy()
    voxp_idx = np.array(voxp_idx)
    voxp_idx_s = [''.join([str(i[0]), str(i[1]), str(i[2])]) for i in voxp_idx]
    # m3t = m3s.copy()

    # print('Number of voxels ocupied by points cloud: \t %i' %(m3p.sum()))
    # m3pidx = np.where(m3p)
    # print(voxp_idx)
    # print(len(voxp_idx))

    totvox = (~m3s).sum()
    AABB2vgidx = lambda boxes: [voxs.get_voxel(pyrr.aabb.centre_point(box)).tolist() for box in boxes]
    # create BB for ray interception
    boxPR = pyrr.aabb.create_from_bounds(minBB, maxBB)
    m3count = np.full_like(m3s, 0, dtype=int)

    outdir = os.path.join(resdir, 'm3s_%s_%s.npy' %(treename, str(voxel_size)))
    outdir_count = os.path.join(resdir, 'm3count_%s_%s.npy' %(treename, str(voxel_size)))

    if show:

        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        for ss in np.unique(sensors, axis=0):
            ax.scatter3D(*ss, color='r', s=20, marker='*')

        positions = [(minBB[0], minBB[1], minBB[2])]
        sizes = [(width, height, depth)]
        pc = plotCubeAt2(positions,sizes,colors=[1,0,0,0.2], edgecolor="k")
        ax.add_collection3d(pc)

        # ax.set_xlim([-18,18])
        # ax.set_ylim([-18,18])
        # ax.set_zlim([0,20])
    else:
        ax = None

    for p1, p2 in tqdm(zip(points, sensors)):

        line = pyrr.line.create_from_points(p1, p2, dtype=None)
        ray = pyrr.ray.create_from_line(line)
        res = pyrr.geometric_tests.ray_intersect_aabb(ray, boxPR)

        if res is not None:

            # print('In PR!!!')

            boxes = intercept(ray, boxPR, voxel_size)

            try:
                # get voxel grid IDX from AABB
                idx = np.array(AABB2vgidx(boxes))
                idx_s = [''.join([str(i[0]), str(i[1]), str(i[2])]) for i in idx]
                # Does voxel where ray pass trhough is in a voxel occupied by point cloud?
                inm3p = np.in1d(idx_s, voxp_idx_s)


                # print('voxp_idx', voxp_idx)
                # print('len voxp_idx', len(voxp_idx_s))
                
                # inm3p = [i in np.array(voxp_idx) for i in idx]
                # for i in idx:
                #     if i in voxp_idx:
                #         print(i, voxp_idx[voxp_idx == i])
                # inm3p = np.array(inm3p)
                # print('len inm3p', len(inm3p), len(idx), len(idx_s))
                # print('# matches:', np.sum(inm3p))
                # print(inm3p)

                inmin = np.zeros(len(inm3p), dtype=bool)
                voxkeep = np.ones(len(inm3p), dtype=bool)

                if inm3p.any() and np.sum(inm3p) < len(idx_s):
                    # print('len idx', len(idx_s))
                    # print('# matches:', np.sum(inm3p))
                    
                    # get the distances from all boxes to the source point (i.e. sensors)
                    voxel_distance = np.array([np.linalg.norm(p2 - pyrr.aabb.centre_point(box).tolist()) for box in boxes])
                    
                    # Find distance to closest voxels with attribute 1
                    dist_min = np.min(np.unique(voxel_distance[inm3p]))
                    inmin = voxel_distance == dist_min

                    # keep voxels with distance greater than distance to closest voxel with attribute 1
                    voxkeep = voxel_distance < dist_min
                    
                elif np.sum(inm3p) == len(idx_s):
                    continue
                    
                # else:
                    # print('No Match!!!')

                if not voxkeep.any():
                    # print('voxkeep is FALSE!!!')
                    continue


                # 3D array with True where all rays pass trhough
                m3s[idx[voxkeep].T[0], idx[voxkeep].T[1], idx[voxkeep].T[2]] = True
                m3s2[idx.T[0], idx.T[1], idx.T[2]] = True
                m3count[idx.T[0], idx.T[1], idx.T[2]] += 1
            except Exception as e:
                print(e)

            if show:

                for box, isinm3p, isinmin, isvoxkeep in zip(boxes, inm3p, inmin, voxkeep):

                    minBB, maxBB = box
                    minBB = np.array(minBB)
                    maxBB = np.array(maxBB)
                    width, height, depth = maxBB - minBB
                    # plot bounding box
                    positions = [(minBB[0], minBB[1], minBB[2])]
                    sizes = [(width, height, depth)]

                    if isinmin:
                        pc = plotCubeAt2(positions,sizes,colors=[1,0,0,0.4], edgecolor="k")
                    elif isinm3p and not isinmin:
                        pc = plotCubeAt2(positions,sizes,colors=[0,0,1,0.4], edgecolor="k")
                    elif isvoxkeep:
                        pc = plotCubeAt2(positions,sizes,colors=[0,1,0,0.4], edgecolor="k")
                    else:
                        pc = plotCubeAt2(positions,sizes,colors=[1,0,1,0.4], edgecolor="k")
                    ax.add_collection3d(pc)

                ax.plot(*line.T.tolist())
                ax.scatter3D(*p1, c='g', s=10)
                ax.scatter3D(*res, c='k', s=10)

        # else:
        #     print('Not in PR!!!!')
    if show: 
        plt.show()

    print('tot vox: \t %i' %(totvox))
    print('voxels hitted: \t %i' %(m3s.sum()))
    print('Percentage of voxels hitted by beam: %.2f' %(m3s.sum()/totvox))

    print('voxels hitted (OLD): \t %i' %(m3s2.sum()))
    print('Percentage of voxels hitted by beam (OLD): %.2f' %(m3s2.sum()/totvox))

    np.save(outdir, m3s)
    np.save(outdir_count, m3count)

    return m3s


def main2(points, sensors, pointsPR, voxel_size, resdir, treename, PRbounds, show=False):

    # voxPR, minBB, maxBB = prAABB(pointsPR, voxel_size)
    # width, height, depth = maxBB - minBB

    # Create voxel of plant region
    # width, height, depth = PRbounds[1] - PRbounds[0]
    # voxPR = o3d.geometry.VoxelGrid.create_dense(origin=PRbounds[0], color=np.array([0,0,1]), voxel_size=voxel_size, width=width, height=height, depth=depth)

    pcd = loads.points2pcd(pointsPR)
    voxPR = o3d.geometry.VoxelGrid.create_from_point_cloud_within_bounds(pcd, voxel_size=voxel_size, min_bound=PRbounds[0], max_bound=PRbounds[1])
    width, height, depth = PRbounds[1] - PRbounds[0]

    # Get 3D-boolean-array of plant region dimmensions and solid voxel
    m3s, voxs, voxp_idx = get_matPR(vox=voxPR, voxel_size=voxel_size)
    m3s2 = m3s.copy()
    voxp_idx = np.array(voxp_idx)
    voxp_idx_s = [''.join([str(i[0]), str(i[1]), str(i[2])]) for i in voxp_idx]

    totvox = (~m3s).sum()
    AABB2vgidx = lambda boxes: [voxs.get_voxel(pyrr.aabb.centre_point(box)).tolist() for box in boxes]
    # create BB for ray interception
    boxPR = pyrr.aabb.create_from_bounds(PRbounds[0], PRbounds[1])
    m3count = np.full_like(m3s, 0, dtype=int)

    outdir = os.path.join(resdir, 'm3s_%s_%s.npy' %(treename, str(voxel_size)))
    outdir_count = os.path.join(resdir, 'm3count_%s_%s.npy' %(treename, str(voxel_size)))

    if show:

        fig = plt.figure()
        ax = fig.add_subplot(111, projection='3d')

        for ss in np.unique(sensors, axis=0):
            ax.scatter3D(*ss, color='r', s=20, marker='*')

        positions = [(PRbounds[0][0], PRbounds[0][1], PRbounds[0][2])]
        sizes = [(width, height, depth)]
        pc = plotCubeAt2(positions,sizes,colors=[1,0,0,0.2], edgecolor="k")
        ax.add_collection3d(pc)

    else:
        ax = None

    for p1, p2 in tqdm(zip(points, sensors)):

        line = pyrr.line.create_from_points(p1, p2, dtype=None)
        ray = pyrr.ray.create_from_line(line)
        res = pyrr.geometric_tests.ray_intersect_aabb(ray, boxPR)

        if res is not None:

            boxes = intercept(ray, boxPR, voxel_size)

            try:
                # get voxel grid IDX from AABB
                idx = np.array(AABB2vgidx(boxes))
                idx_s = [''.join([str(i[0]), str(i[1]), str(i[2])]) for i in idx]
                # Does voxel where ray pass trhough is in a voxel occupied by point cloud?
                inm3p = np.in1d(idx_s, voxp_idx_s)


                inmin = np.zeros(len(inm3p), dtype=bool)
                voxkeep = np.ones(len(inm3p), dtype=bool)

                if inm3p.any() and np.sum(inm3p) < len(idx_s):
                    
                    # get the distances from all boxes to the source point (i.e. sensors)
                    voxel_distance = np.array([np.linalg.norm(p2 - pyrr.aabb.centre_point(box).tolist()) for box in boxes])
                    
                    # Find distance to closest voxels with attribute 1
                    dist_min = np.min(np.unique(voxel_distance[inm3p]))

                    # keep voxels with distance greater than distance to closest voxel with attribute 1
                    voxkeep = voxel_distance < dist_min

                    # Find the attribute 1 voxel where the beam first intercept with.
                    inmin = voxel_distance == dist_min
                    
                elif np.sum(inm3p) == len(idx_s):
                    continue

                if not voxkeep.any():
                    continue

                # Counts
                # 3D array with True where all rays pass trhough
                m3s[idx[voxkeep].T[0], idx[voxkeep].T[1], idx[voxkeep].T[2]] = True
                # m3s2[idx.T[0], idx.T[1], idx.T[2]] = True

                # count incidences only for voxels with points
                m3count[idx[inmin].T[0], idx[inmin].T[1], idx[inmin].T[2]] += 1

            except Exception as e:
                print(e)

            # For plot only
            if show:

                for box, isinm3p, isinmin, isvoxkeep in zip(boxes, inm3p, inmin, voxkeep):

                    minBB, maxBB = box
                    minBB = np.array(minBB)
                    maxBB = np.array(maxBB)
                    width, height, depth = maxBB - minBB
                    # plot bounding box
                    positions = [(minBB[0], minBB[1], minBB[2])]
                    sizes = [(width, height, depth)]

                    if isinmin:
                        pc = plotCubeAt2(positions,sizes,colors=[1,0,0,0.4], edgecolor="k")
                    elif isinm3p and not isinmin:
                        pc = plotCubeAt2(positions,sizes,colors=[0,0,1,0.4], edgecolor="k")
                    elif isvoxkeep:
                        pc = plotCubeAt2(positions,sizes,colors=[0,1,0,0.4], edgecolor="k")
                    else:
                        pc = plotCubeAt2(positions,sizes,colors=[1,0,1,0.4], edgecolor="k")
                    ax.add_collection3d(pc)

                ax.plot(*line.T.tolist())
                ax.scatter3D(*p1, c='g', s=10)
                ax.scatter3D(*res, c='k', s=10)

        # else:
            # print('Not in PR!!!!')
    if show: 
        plt.show()

    print('tot vox: \t %i' %(totvox))
    print('voxels hitted: \t %i' %(m3s.sum()))
    print('Percentage of voxels hitted by beam: %.2f' %(m3s.sum()/totvox))

    print('voxels hitted (OLD): \t %i' %(m3s2.sum()))
    print('Percentage of voxels hitted by beam (OLD): %.2f' %(m3s2.sum()/totvox))

    np.save(outdir, m3s)
    np.save(outdir_count, m3count)

    return m3s
