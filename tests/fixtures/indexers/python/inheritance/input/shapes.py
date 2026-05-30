"""Inheritance fixture: single-base subclass + multiple bases."""


class Shape:
    def area(self):
        return 0


class Drawable:
    def draw(self):
        pass


class Square(Shape):
    def area(self):
        return self.side * self.side


class Sprite(Shape, Drawable):
    pass
