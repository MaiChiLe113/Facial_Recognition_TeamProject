# Measuring Room 204 (origin = floor point under CAM 1)

One picture per part: `figures/plan_A.png` … `figures/plan_D.png`.

- Units are metres, rounded to the cm. Only measure **straight tape distances between two points**; `survey.py` computes
  x, y by trilateration.
- Write each value after its `:` in `data/result.yaml` (the `# N.` headers there are the step numbers below).
- Cameras do not see all around: put markers only inside the shaded areas of the pictures.

Point names: `O` = origin under CAM 1. `P0` = spot on the room wall straight across from `O`. `M3` = centre of
marker 3. `D7` = top-left corner of desk D7's top (near the room wall, far from the door). `door_top` = door edge on the
corridor side, `door_top_in` = the same edge on the room side.

## A. Preparation (`figures/plan_A.png`)

1. Hang a plumb line from CAM 1 and tape-mark the floor under it: this is `O`.
2. Run the tape from `O` at a right angle to the base of the room wall and mark `P0` (check the angle with 3-4-5): `x_wall`.
3. Measure the wall thickness in the doorway: `wall_thickness`.
4. Measure the **y** of the wall edges: put the tape end at `P0` (y = 0) and run it along the wall base towards the door:
   `glass_top`, `glass_bottom`, `door_top`, `door_bottom` (negative for an edge above `P0`).
5. Print the 7 sheets in `markers/` (IDs 0 and 2–7, DICT_4X4_50) on A4 at 100 %. Place them as in the picture: 4, 5, 6 in
   the corridor, 3 and 7 in the doorway, 0 and 2 on the aisle inside the room.
6. Take a test photo from each camera and run `check_aruco.py <photo> --expect ...` until it passes
   (CAM 1: `3,4,5,6,7`; CAM 2: `0,2,3,7`).

## B. Marker distances (`figures/plan_B.png`)

7. Marker 4: `O-M4`, `P0-M4`
8. Marker 5: `O-M5`, `P0-M5`
9. Marker 6: `O-M6`, `P0-M6`, `door_top-M6`
10. Marker 3: `O-M3`, `door_top-M3`, `door_bottom-M3`
11. Marker 7: `O-M7`, `door_top-M7`, `door_bottom-M7`, `M3-M7`
12. Marker 0: `M3-M0`, `M7-M0`, `door_bottom_in-M0`
13. Marker 2: `M0-M2`, `M7-M2`, `glass_bottom_in-M2`
14. With nobody in the frame, take one 1280×720 photo per camera.

## C. Desks D1, D3, D5, D7, the ones CAM 2 sees (`figures/plan_C.png`)

15. Desk top size (all desks are the same): `desk_L` (length, at a right angle to the room wall), `desk_W` (width).
16. Desk D7: `M3-D7`, `M0-D7`, `door_top_in-D7`
17. Desk D5: `D7-D5`, `door_top_in-D5`, `glass_bottom_in-D5`
18. Desk D3: `D5-D3`, `glass_bottom_in-D3`, `glass_top_in-D3`
19. Desk D1: `D3-D1`, `glass_top_in-D1`, `P0_in-D1`

## D. Cameras (`figures/plan_D.png`)

20. Floor point under CAM 2: `glass_top_in-CAM2`, `M2-CAM2`, `M0-CAM2`

## E. Solve

21. Run `survey.py`. Re-measure every line marked `<- check this one`; for a point marked `<- uncertain`, add a distance
    from another direction.

## Optional

Not used to compute x, y. Camera heights, when filled in, are used as a prior in `fit_floor.py`.

- Desk height from the floor: `desk_height`
- Floor to lens centre: `cam1_height`, `cam2_height`
