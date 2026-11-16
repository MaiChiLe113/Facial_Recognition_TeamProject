// MOCK past sessions for the Class and History pages, used until the backend serves GET /api/sessions.
// Each entry has the same shape the backend should return (see fetchSessions in api.js).
// The current session comes from data/mock/session.json and is added in api.js.
const none = { global_id: null, status: 'not_seen', check_in: null, entry: null, exit: null, minutes: null }

export default [
  {
    id: '2026-11-11-1', course_key: 1, room: '204', date: '2026-11-11', start: '08:00', end: '12:00',
    attendance: [
      { student_id_vn: 'SWH02378', global_id: 2, status: 'left', check_in: '08:05', entry: '08:06', exit: '11:52', minutes: 226 },
      { student_id_vn: 'SWH02701', global_id: 4, status: 'left', check_in: '08:12', entry: '08:13', exit: '11:50', minutes: 217 },
      { student_id_vn: 'SWH02803', global_id: 5, status: 'left', check_in: '08:20', entry: '08:21', exit: '10:02', minutes: 101 },
      { student_id_vn: 'SWH02486', ...none },
    ],
    events: [
      { time: '11:52', event: 'Le Mai Chi left class', source: 'cam_2', student_id: 'SWH02378' },
      { time: '11:50', event: 'Nguyen Duc Manh left class', source: 'cam_2', student_id: 'SWH02701' },
      { time: '10:02', event: 'Do Trinh Thuan Minh left class', source: 'cam_2', student_id: 'SWH02803' },
      { time: '08:21', event: 'Do Trinh Thuan Minh entered class', source: 'cam_2', student_id: 'SWH02803' },
      { time: '08:20', event: 'Do Trinh Thuan Minh checked in', source: 'attendance_cam', student_id: 'SWH02803' },
      { time: '08:13', event: 'Nguyen Duc Manh entered class', source: 'cam_2', student_id: 'SWH02701' },
      { time: '08:12', event: 'Nguyen Duc Manh checked in', source: 'attendance_cam', student_id: 'SWH02701' },
      { time: '08:06', event: 'Le Mai Chi entered class', source: 'cam_2', student_id: 'SWH02378' },
      { time: '08:05', event: 'Le Mai Chi checked in', source: 'attendance_cam', student_id: 'SWH02378' },
    ],
  },
  {
    id: '2026-11-11-2', course_key: 2, room: '204', date: '2026-11-11', start: '13:00', end: '17:00',
    attendance: [
      { student_id_vn: 'SWH02378', global_id: 1, status: 'left', check_in: '13:02', entry: '13:03', exit: '16:40', minutes: 217 },
    ],
    events: [
      { time: '16:40', event: 'Le Mai Chi left class', source: 'cam_2', student_id: 'SWH02378' },
      { time: '13:03', event: 'Le Mai Chi entered class', source: 'cam_2', student_id: 'SWH02378' },
      { time: '13:02', event: 'Le Mai Chi checked in', source: 'attendance_cam', student_id: 'SWH02378' },
    ],
  },
  {
    id: '2026-11-04-1', course_key: 1, room: '204', date: '2026-11-04', start: '08:00', end: '12:00',
    attendance: [
      { student_id_vn: 'SWH02378', global_id: 3, status: 'left', check_in: '08:10', entry: '08:11', exit: '11:45', minutes: 214 },
      { student_id_vn: 'SWH02701', global_id: 6, status: 'checked_in', check_in: '08:40', entry: null, exit: null, minutes: null },
      { student_id_vn: 'SWH02803', ...none },
      { student_id_vn: 'SWH02486', ...none },
    ],
    events: [
      { time: '11:45', event: 'Le Mai Chi left class', source: 'cam_2', student_id: 'SWH02378' },
      { time: '08:40', event: 'Nguyen Duc Manh checked in', source: 'attendance_cam', student_id: 'SWH02701' },
      { time: '08:31', event: 'Spoof attempt rejected (phone screen)', source: 'attendance_cam', student_id: null },
      { time: '08:11', event: 'Le Mai Chi entered class', source: 'cam_2', student_id: 'SWH02378' },
      { time: '08:10', event: 'Le Mai Chi checked in', source: 'attendance_cam', student_id: 'SWH02378' },
    ],
  },
]
