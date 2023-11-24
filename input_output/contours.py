import os
import json
import glob

import numpy as np
import matplotlib.path as mplPath
from loguru import logger
from skimage.draw import polygon2mask
from PyQt5.QtWidgets import (
    QErrorMessage,
)
from PyQt5.QtCore import Qt
from skimage import measure

from version import version_file_str
from input_output.read_xml import read_xml
from input_output.write_xml import write_xml


def read_contours(main_window, file_name=None):
    """Reads contours saved in json/xml format and displays the contours in the graphics scene"""
    success = False
    json_files = glob.glob(f'{file_name}_contours*.json')
    xml_files = glob.glob(f'{file_name}_contours*.xml')

    if not main_window.use_xml_files and json_files:  # json files have priority over xml unless desired
        newest_json = max(json_files)  # find file with most recent version
        logger.info(f'Current version is {version_file_str}, file found with most recent version is {newest_json}')
        with open(newest_json, 'r') as in_file:
            main_window.data = json.load(in_file)
        success = True

    elif xml_files:
        newest_xml = max(xml_files)  # find file with most recent version
        logger.info(f'Current version is {version_file_str}, file found with most recent version is {newest_xml}')
        read_xml(main_window, newest_xml)
        main_window.data['lumen'] = map_to_list(main_window.data['lumen'])
        for key in ['lumen_area', 'lumen_circumf', 'longest_distance', 'shortest_distance']:
            main_window.data[key] = [0] * main_window.metadata[
                'num_frames'
            ]  # initialise empty containers for data not stored in xml
        for key in ['lumen_centroid', 'farthest_point', 'nearest_point']:
            main_window.data[key] = (
                [[] for _ in range(main_window.metadata['num_frames'])],
                [[] for _ in range(main_window.metadata['num_frames'])],
            )  # initialise empty containers for data not stored in xml
        success = True

    if success:
        main_window.contours_drawn = True
        main_window.display.set_data(main_window.data['lumen'], main_window.images)
        main_window.hide_contours_box.setChecked(False)

    return success


def write_contours(main_window):
    """Writes contours to a json/xml file"""

    if not main_window.image_displayed:
        warning = QErrorMessage(main_window)
        warning.setWindowModality(Qt.WindowModal)
        warning.showMessage('Cannot write contours before reading DICOM file')
        warning.exec_()
        return

    if main_window.use_xml_files:
        # reformat data for compatibility with write_xml function
        x, y = [], []
        for i in range(main_window.metadata['num_frames']):
            if i < len(main_window.data['lumen'][0]):
                new_x_lumen = main_window.data['lumen'][0][i]
                new_y_lumen = main_window.data['lumen'][1][i]
            else:
                new_x_lumen = []
                new_y_lumen = []

            x.append(new_x_lumen)
            y.append(new_y_lumen)

        write_xml(
            x,
            y,
            main_window.images.shape,
            main_window.metadata['resolution'],
            main_window.ivusPullbackRate,
            main_window.data['plaque_frames'],
            main_window.data['phases'],
            main_window.file_name,
        )
    else:
        with open(os.path.join(main_window.file_name + f'_contours_{version_file_str}.json'), 'w') as out_file:
            json.dump(main_window.data, out_file)


def segment(main_window):
    """Segmentation and phenotyping of IVUS images"""
    main_window.status_bar.showMessage('Segmenting all gated frames...')
    if not main_window.image_displayed:
        warning = QErrorMessage(main_window)
        warning.setWindowModality(Qt.WindowModal)
        warning.showMessage('Cannot perform automatic segmentation before reading DICOM file')
        warning.exec_()
        main_window.status_bar.showMessage('Waiting for user input')
        return

    masks = main_window.predictor(main_window.images)
    main_window.metrics = compute_area(main_window, masks)
    main_window.data['lumen'] = mask_to_contours(masks)
    main_window.contours_drawn = True
    main_window.display.set_data(main_window.data['lumen'], main_window.images)
    main_window.hide_contours_box.setChecked(False)
    main_window.status_bar.showMessage('Waiting for user input')


def new_spline(main_window):
    if not main_window.image_displayed:
        warning = QErrorMessage(main_window)
        warning.setWindowModality(Qt.WindowModal)
        warning.showMessage('Cannot create manual contour before reading DICOM file')
        warning.exec_()
        return

    main_window.display.new_contour(main_window)
    main_window.hide_contours_box.setChecked(False)
    main_window.contours_drawn = True


def mask_to_contours(masks):
    """Convert numpy mask to IVUS contours"""
    lumen_pred = get_contours(masks, image_shape=masks.shape[1:3])
    lumen_pred = downsample(lumen_pred)

    return lumen_pred


def get_contours(preds, image_shape):
    """Extracts contours from masked images. Returns x and y coodinates"""
    lumen_pred = [[], []]
    for frame in range(preds.shape[0]):
        if np.any(preds[frame, :, :] == 1):
            lumen = label_contours(preds[frame, :, :])
            keep_lumen_x, keep_lumen_y = keep_largest_contour(lumen, image_shape)
            lumen_pred[0].append(keep_lumen_x)
            lumen_pred[1].append(keep_lumen_y)
        else:
            lumen_pred[0].append([])
            lumen_pred[1].append([])

    return lumen_pred


def label_contours(image):
    """generate contours for labels"""
    contours = measure.find_contours(image)
    lumen = []
    for contour in contours:
        lumen.append(np.array((contour[:, 0], contour[:, 1])))

    return lumen


def keep_largest_contour(contours, image_shape):
    max_length = 0
    keep_contour = [[], []]
    for contour in contours:
        if keep_valid_contour(contour, image_shape):
            if len(contour[0]) > max_length:
                keep_contour = [list(contour[1, :]), list(contour[0, :])]
                max_length = len(contour[0])

    return keep_contour


def keep_valid_contour(contour, image_shape):
    """Contour is valid if it contains the centroid of the image"""
    bbPath = mplPath.Path(np.transpose(contour))
    centroid = [image_shape[0] // 2, image_shape[1] // 2]
    return bbPath.contains_point(centroid)


def downsample(contours, num_points=20):
    """Downsamples input contour data by selecting n points from original contour"""
    num_frames = len(contours[0])
    downsampled = [[] for _ in range(num_frames)], [[] for _ in range(num_frames)]

    for frame in range(num_frames):
        if contours[0][frame]:
            points_to_sample = range(0, len(contours[0][frame]), len(contours[0][frame]) // num_points)
            for axis in range(2):
                downsampled[axis][frame] = [contours[axis][frame][point] for point in points_to_sample]
    return downsampled


def contours_to_mask(images, contoured_frames, lumen):
    """Convert IVUS contours to numpy mask"""
    image_shape = images.shape[1:3]
    mask = np.zeros_like(images)
    for i, frame in enumerate(contoured_frames):
        try:
            lumen_polygon = [[x, y] for x, y in zip(lumen[1][frame], lumen[0][frame])]
            mask[i, :, :] += polygon2mask(image_shape, lumen_polygon).astype(np.uint8)
        except ValueError:  # frame has no lumen contours
            pass
    mask = np.clip(mask, a_min=0, a_max=1)  # enforce correct value range

    return mask


def compute_area(main_window, masks):
    lumen_area = np.sum(masks == 1, axis=(1, 2)) * main_window.metadata['resolution'] ** 2

    return lumen_area


def map_to_list(contours):
    """Converts map to list"""
    x, y = contours
    x = [list(x[i]) for i in range(0, len(x))]
    y = [list(y[i]) for i in range(0, len(y))]

    return (x, y)
