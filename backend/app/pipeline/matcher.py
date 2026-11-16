"""Cross-camera matching -> one global ID per person.  Owner: Mai Chi (innovation feature)

Global IDs are plain numbers in order of appearance (1, 2, 3 ...), known or unknown,
and never change. A name is attached after the attendance cam verifies the face.

Techniques to combine (design doc section 6):
  T1 ground-plane homography -> position on the 2D room map
  T2 time + door-zone handoff (attendance cam -> CAM2 entry zone)
  T3 appearance re-ID (OSNet body embeddings)
  T4 opportunistic face check on CAM2
"""


class GlobalMatcher:
    def __init__(self):
        self.next_id = 1
        self.names = {}            # global_id -> student name

    def new_global_id(self):
        gid = self.next_id
        self.next_id += 1
        return gid

    def assign(self, cam_id, local_tracks, timestamp):
        """Map each local track to a global ID. Return [{"global_id", "box", "map_xy"}].

        TODO: T1-T4.
        """
        raise NotImplementedError

    def attach_name(self, global_id, name):
        self.names[global_id] = name
