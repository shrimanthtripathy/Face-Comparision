import threading
import numpy as np
import pytest
from backend import engine as E

class Face:
    def __init__(self, box, score=0.9): self.bbox, self.det_score, self.normed_embedding, self.age = box, score, np.array([1.0, 0]), 30

def test_central_rule_beats_largest_when_a_companion_is_bigger():
    boxes = [[0, 0, 120, 120], [80, 70, 180, 170]]          # a big face at the edge, the target near the centre of a 250 px image
    assert E.pick_index(boxes, 250, 250, "largest") == 0 and E.pick_index(boxes, 250, 250, "central") == 1

def test_substantial_ignores_small_or_low_confidence_faces():
    fs = [Face([0, 0, 100, 100]), Face([200, 0, 230, 30]), Face([300, 0, 400, 100], 0.4)]
    assert len(E.substantial(fs)) == 1
    assert len(E.substantial([Face([0, 0, 100, 100]), Face([120, 0, 210, 90])])) == 2

class Arc:
    def __init__(self, by_height): self.by_height = by_height
    def get(self, img): return self.by_height[img.shape[0]]

def _eng(by_height):
    e = E.Engine.__new__(E.Engine); e.lock = threading.Lock(); e.arc = Arc(by_height); e.mesh = None; return e
A, B = np.zeros((50, 50, 3), np.uint8), np.zeros((40, 40, 3), np.uint8)
two = [Face([0, 0, 20, 20]), Face([25, 0, 45, 20])]; one = [Face([5, 5, 35, 35])]

def test_two_similar_faces_in_either_image_are_refused_not_guessed():
    with pytest.raises(E.AmbiguousFaces, match="Image A"): _eng({50: two, 40: one}).compare(A, B, {}, {})
    with pytest.raises(E.AmbiguousFaces, match="Image B"): _eng({50: one, 40: two}).compare(A, B, {}, {})

def test_a_chosen_face_skips_the_check_for_A_only():
    with pytest.raises(E.AmbiguousFaces, match="Image B"): _eng({50: two, 40: two}).compare(A, B, {}, {}, None, True)
