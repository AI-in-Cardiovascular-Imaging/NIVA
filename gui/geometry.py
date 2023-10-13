import numpy as np
from loguru import logger
from scipy.interpolate import splprep, splev
from PyQt5.QtWidgets import QGraphicsEllipseItem, QGraphicsPathItem
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPen, QPainterPath


class Point(QGraphicsEllipseItem):
    """Class that describes a spline point"""

    def __init__(self, pos, line_thickness=1, point_radius=10, color=None):
        super(Point, self).__init__()
        self.line_thickness = line_thickness
        self.point_radius = point_radius

        if color == 'y':
            self.defaultColor = QPen(Qt.yellow, self.line_thickness)
        elif color == 'r':
            self.defaultColor = QPen(Qt.red, self.line_thickness)
        elif color == "g":
            self.defaultColor = QPen(Qt.green, self.line_thickness)
        else:
            self.defaultColor = QPen(Qt.blue, self.line_thickness)

        self.setPen(self.defaultColor)
        self.setRect(
            pos[0] - self.point_radius * 0.5, pos[1] - self.point_radius * 0.5, self.point_radius, self.point_radius
        )

    def getPoint(self):
        try:
            return self.rect().x(), self.rect().y()
        except RuntimeError:  # Point has been deleted
            return None, None

    def updateColor(self):
        self.setPen(QPen(Qt.transparent, self.line_thickness))

    def resetColor(self):
        self.setPen(self.defaultColor)

    def update(self, pos):
        """Updates the Point position"""

        self.setRect(
            pos.x(), pos.y(), self.point_radius, self.point_radius
        )
        return self.rect()


class Spline(QGraphicsPathItem):
    """Class that describes a spline"""

    def __init__(self, points, line_thickness=1, color=None):
        super().__init__()
        self.knotpoints = None
        self.full_contour = None
        self.setKnotPoints(points)

        if color == 'y':
            self.setPen(QPen(Qt.yellow, line_thickness))
        elif color == "r":
            self.setPen(QPen(Qt.red, line_thickness))
        elif color == "g":
            self.setPen(QPen(Qt.green, line_thickness))
        else:
            self.setPen(QPen(Qt.blue, line_thickness))

    def setKnotPoints(self, points):
        try:
            start_point = QPointF(points[0][0], points[1][0])
            self.path = QPainterPath(start_point)
            super(Spline, self).__init__(self.path)

            self.full_contour = self.interpolate(points)
            if self.full_contour[0] is not None:
                for i in range(0, len(self.full_contour[0])):
                    self.path.lineTo(self.full_contour[0][i], self.full_contour[1][i])

                self.setPath(self.path)
                self.path.closeSubpath()
                self.knotpoints = points
        except IndexError:  # no points for this frame
            logger.error(points)
            pass

    def interpolate(self, pts):
        """Interpolates the spline points at 500 points along spline"""
        pts = np.array(pts)
        try:
            tck, u = splprep(pts, u=None, s=0.0, per=1)
        except ValueError:
            return (None, None)
        u_new = np.linspace(u.min(), u.max(), 500)
        x_new, y_new = splev(u_new, tck, der=0)

        return (x_new, y_new)

    def update(self, pos, idx):
        """Updates the stored spline everytime it is moved
        Args:
            pos: new points coordinates
            idx: index on spline of updated point
        """

        if idx == len(self.knotpoints[0]) + 1:
            self.knotpoints[0].append(pos.x())
            self.knotpoints[1].append(pos.y())
        else:
            self.knotpoints[0][idx] = pos.x()
            self.knotpoints[1][idx] = pos.y()
        self.full_contour = self.interpolate(self.knotpoints)
        for i in range(0, len(self.full_contour[0])):
            self.path.setElementPositionAt(i, self.full_contour[0][i], self.full_contour[1][i])
        self.setPath(self.path)
