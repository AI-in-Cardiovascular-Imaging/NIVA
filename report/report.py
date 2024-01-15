import os
import math
import csv

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from loguru import logger
from PyQt5.QtWidgets import QErrorMessage, QProgressDialog
from PyQt5.QtCore import Qt
from shapely.geometry import Polygon
from itertools import combinations

from gui.geometry import Spline


def report(main_window, suppress_messages=False):
    """Writes a report file containing lumen area, etc."""

    if not main_window.image_displayed:
        warning = QErrorMessage(main_window)
        warning.setWindowModality(Qt.WindowModal)
        warning.showMessage('Cannot write report before reading DICOM file')
        warning.exec_()
        return

    contoured_frames = [
        frame for frame in range(main_window.metadata['num_frames']) if main_window.data['lumen'][0][frame]
    ]
    if not contoured_frames:
        warning = QErrorMessage(main_window)
        warning.setWindowModality(Qt.WindowModal)
        warning.showMessage('Cannot write report before drawing contours')
        warning.exec_()
        return

    report_data = compute_all(
        main_window,
        contoured_frames,
        suppress_messages,
        plot=main_window.config.report.plot,
        save_as_csv=main_window.config.report.save_as_csv,
    )
    if report_data is not None:  # else user cancelled progress bar
        report_data.to_csv(
            os.path.splitext(main_window.file_name)[0] + '_report.txt',
            sep='\t',
            float_format='%.2f',
            index=False,
            header=True,
        )

        if not suppress_messages:
            main_window.successMessage('Write report')

    return report_data


def compute_all(main_window, contoured_frames, suppress_messages, plot=True, save_as_csv=True):
    """compute all metrics and plot if desired"""
    if not suppress_messages:
        progress = QProgressDialog(main_window)
        progress.setWindowFlags(Qt.Dialog)
        progress.setModal(True)
        progress.setMinimum(0)
        progress.setMaximum(len(contoured_frames) * (1 + save_as_csv))
        progress.resize(500, 100)
        progress.setValue(0)
        progress.setWindowTitle('Writing report...')
        progress.show()

    longest_distance = main_window.data['longest_distance']
    farthest_x = main_window.data['farthest_point'][0]
    farthest_y = main_window.data['farthest_point'][1]
    shortest_distance = main_window.data['shortest_distance']
    nearest_x = main_window.data['nearest_point'][0]
    nearest_y = main_window.data['nearest_point'][1]
    lumen_area = main_window.data['lumen_area']
    lumen_circumf = main_window.data['lumen_circumf']
    centroid_x = main_window.data['lumen_centroid'][0]
    centroid_y = main_window.data['lumen_centroid'][1]
    try:  # these entries were added later -> might be missing in older data dicts
        elliptic_ratio = main_window.data['elliptic_ratio']
        vector_length = main_window.data['vector_length']
        vector_angle = main_window.data['vector_angle']
    except KeyError:
        elliptic_ratio = [0] * main_window.metadata['num_frames']
        vector_length = [0] * main_window.metadata['num_frames']
        vector_angle = [0] * main_window.metadata['num_frames']
    lumen_x = [[] for _ in range(main_window.metadata['num_frames'])]
    lumen_y = [[] for _ in range(main_window.metadata['num_frames'])]

    for frame in contoured_frames:
        if lumen_area[frame] and elliptic_ratio[frame] != 0:  # values already computed for this frame -> skip
            continue

        lumen_contour = Spline(
            [main_window.data['lumen'][0][frame], main_window.data['lumen'][1][frame]],
            n_points=main_window.config.display.n_points_contour,
        )  # data['lumen'] stores only knot points -> need to recalculate full contour
        lumen_x[frame] = [point for point in lumen_contour.full_contour[0]]
        lumen_y[frame] = [point for point in lumen_contour.full_contour[1]]
        polygon = Polygon([(x, y) for x, y in zip(lumen_x[frame], lumen_y[frame])])
        exterior_coords = polygon.exterior.coords

        lumen_area[frame], lumen_circumf[frame], centroid_x[frame], centroid_y[frame] = compute_polygon_metrics(
            main_window, polygon, frame
        )
        longest_distance[frame], farthest_x[frame], farthest_y[frame] = farthest_points(
            main_window, exterior_coords, frame
        )
        shortest_distance[frame], nearest_x[frame], nearest_y[frame] = closest_points(main_window, polygon, frame)
        if shortest_distance[frame] != 0:
            elliptic_ratio[frame] = longest_distance[frame] / shortest_distance[frame]
        vector_length[frame], vector_angle[frame] = centroid_center_vector(
            main_window, centroid_x[frame], centroid_y[frame]
        )
        if not suppress_messages:
            progress.setValue(frame)
            if progress.wasCanceled():
                return None

    report_data = pd.DataFrame()
    report_data['frame'] = contoured_frames
    report_data['position'] = [main_window.metadata['pullback_length'][frame] for frame in contoured_frames]
    report_data['phase'] = [main_window.data['phases'][frame] for frame in contoured_frames]
    report_data['lumen_area'] = [lumen_area[frame] for frame in contoured_frames]
    report_data['lumen_circumf'] = [lumen_circumf[frame] for frame in contoured_frames]
    report_data['longest_distance'] = [longest_distance[frame] for frame in contoured_frames]
    report_data['shortest_distance'] = [shortest_distance[frame] for frame in contoured_frames]
    report_data['elliptic_ratio'] = [elliptic_ratio[frame] for frame in contoured_frames]
    report_data['vector_length'] = [vector_length[frame] for frame in contoured_frames]
    report_data['vector_angle'] = [vector_angle[frame] for frame in contoured_frames]
    main_window.data['elliptic_ratio'] = elliptic_ratio
    main_window.data['vector_length'] = vector_length
    main_window.data['vector_angle'] = vector_angle

    if save_as_csv:  # write centered contours to .csv files
        csv_out_dir = os.path.join(main_window.file_name + '_csv_files')
        os.makedirs(csv_out_dir, exist_ok=True)

        for frame in contoured_frames:
            if not lumen_x[frame]:
                lumen_contour = Spline(
                    [main_window.data['lumen'][0][frame], main_window.data['lumen'][1][frame]],
                    n_points=main_window.config.display.n_points_contour,
                )
                lumen_x[frame] = [point for point in lumen_contour.full_contour[0]]
                lumen_y[frame] = [point for point in lumen_contour.full_contour[1]]
            with open(os.path.join(csv_out_dir, f'{frame}_contours.csv'), 'w', newline='') as csv_file:
                writer = csv.writer(csv_file, delimiter='\t')
                rows = zip(
                    [(x - centroid_x[frame]) * main_window.metadata['resolution'] for x in lumen_x[frame]],
                    [(y - centroid_y[frame]) * main_window.metadata['resolution'] for y in lumen_y[frame]],
                )  # csv can only write rows, not columns directly
                for row in rows:
                    writer.writerow(row)
            if not suppress_messages:
                progress.setValue(len(contoured_frames) + frame)
                if progress.wasCanceled():
                    return report_data
    if not suppress_messages:
        progress.close()

    if plot:
        first_third = int(len(contoured_frames) * 0.25)
        second_third = int(len(contoured_frames) * 0.5)
        third_third = int(len(contoured_frames) * 0.75)
        indices_to_plot = [first_third, second_third, third_third]
        frames_to_plot = [contoured_frames[frame] for frame in indices_to_plot]

        for frame in frames_to_plot:
            plt.figure(figsize=(6, 6))
            plt.plot(
                lumen_x[frame],
                lumen_y[frame],
                '-g',
                linewidth=2,
                label='Contour',
            )
            plt.plot(centroid_x[frame], centroid_y[frame], 'ro', markersize=8, label='Centroid')
            plt.plot(farthest_x[frame][0], farthest_y[frame][0], 'bo', markersize=8, label='Farthest Point 1')
            plt.plot(farthest_x[frame][1], farthest_y[frame][1], 'bo', markersize=8, label='Farthest Point 2')
            plt.plot(nearest_x[frame][0], nearest_y[frame][0], 'yo', markersize=8, label='Nearest Point 1')
            plt.plot(nearest_x[frame][1], nearest_y[frame][1], 'yo', markersize=8, label='Nearest Point 2')

            # Annotate with shortest and longest distances
            plt.annotate(
                f'Shortest Distance: {shortest_distance[frame]:.2f} mm',
                xy=(centroid_x[frame], centroid_y[frame]),
                xycoords='data',
                xytext=(10, 30),
                textcoords='offset points',
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=.2'),
            )

            plt.annotate(
                f'Longest Distance: {longest_distance[frame]:.2f} mm',
                xy=(centroid_x[frame], centroid_y[frame]),
                xycoords='data',
                xytext=(10, -30),
                textcoords='offset points',
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=-.2'),
            )

            plt.annotate(
                f'Lumen Area: {lumen_area[frame]:.2f} mm\N{SUPERSCRIPT TWO}\nElliptic Ratio: {longest_distance[frame]/shortest_distance[frame]:.2f}',
                xy=(centroid_x[frame], centroid_y[frame]),
                xycoords='data',
                xytext=(10, 0),
                textcoords='offset points',
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'),
            )

            plt.title(f'Frame {frame + 1}')
            plt.legend(loc='upper right')
            plt.gca().invert_yaxis()
            plt.grid()
            plt.tight_layout()
            plt.show()

    return report_data


def compute_polygon_metrics(main_window, polygon, frame):
    """Computes lumen area and centroid from contour"""
    lumen_area = polygon.area * main_window.metadata['resolution'] ** 2
    lumen_circumf = polygon.length * main_window.metadata['resolution']
    centroid_x = polygon.centroid.x
    centroid_y = polygon.centroid.y
    main_window.data['lumen_area'][frame] = lumen_area
    main_window.data['lumen_circumf'][frame] = lumen_circumf
    main_window.data['lumen_centroid'][0][frame] = centroid_x
    main_window.data['lumen_centroid'][1][frame] = centroid_y

    return lumen_area, lumen_circumf, centroid_x, centroid_y


def centroid_center_vector(window, centroid_x, centroid_y):
    """Returns the length and angle of a vector from the center of the image to the centroid"""
    center_x = window.images.shape[1] / 2
    center_y = window.images.shape[2] / 2

    unit_vector = np.array([0, 1])
    vector = np.array([centroid_x - center_x, centroid_y - center_y])

    vector_length = np.linalg.norm(vector) * window.metadata['resolution']

    vector_dot = np.dot(unit_vector, vector)
    vector_det = np.linalg.det(np.array([unit_vector, vector]))
    vector_angle = np.arctan2(vector_det, vector_dot)
    vector_angle = np.degrees(vector_angle)

    if vector_angle < 0:
        vector_angle += 360

    return vector_length, vector_angle


def farthest_points(main_window, exterior_coords, frame):
    max_distance = 0
    farthest_points = None

    for point1, point2 in combinations(exterior_coords, 2):
        distance = math.dist(point1, point2)
        if distance > max_distance:
            max_distance = distance
            farthest_points = (point1, point2)

    longest_distance = max_distance * main_window.metadata['resolution']

    # Separate x and y coordinates and append to the respective lists
    x1, y1 = farthest_points[0]
    x2, y2 = farthest_points[1]
    farthest_point_x = [x1, x2]
    farthest_point_y = [y1, y2]

    main_window.data['longest_distance'][frame] = longest_distance
    main_window.data['farthest_point'][0][frame] = farthest_point_x
    main_window.data['farthest_point'][1][frame] = farthest_point_y

    return longest_distance, farthest_point_x, farthest_point_y


def closest_points(main_window, polygon, frame):
    contour = polygon.exterior.coords
    num_points = len(contour)
    min_distance = math.inf
    closest_points = None

    index_1 = 0
    index_2 = num_points // 2

    while True:
        distance = math.dist(contour[index_1], contour[index_2])
        if distance < min_distance:
            min_distance = distance
            closest_points = (contour[index_1], contour[index_2])

        index_1 += 1
        index_2 += 1

        if index_1 >= num_points // 2:
            break

    shortest_distance = min_distance * main_window.metadata['resolution']

    # Separate x and y coordinates and append to the respective lists
    try:
        x1, y1 = closest_points[0]
        x2, y2 = closest_points[1]
        closest_point_x = [x1, x2]
        closest_point_y = [y1, y2]
    except TypeError:  # closest_points might be None for some very weird shapes
        logger.warning('No closest points found, probably due to polygon shape')
        closest_point_x = [0, 0]
        closest_point_y = [0, 0]
        shortest_distance = 0

    main_window.data['shortest_distance'][frame] = shortest_distance
    main_window.data['nearest_point'][0][frame] = closest_point_x
    main_window.data['nearest_point'][1][frame] = closest_point_y

    return shortest_distance, closest_point_x, closest_point_y
