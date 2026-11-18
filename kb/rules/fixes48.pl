/*  Phase 4.8 step 1 (owner, 2026-11-18): rule-only fixes for wrong dev2 answers.

    - Expressway ban and speed (dev2 train_466). Law 36/2024 art. 25.3: "xe mô tô, xe gắn máy,
      các loại xe tương tự xe mô tô, xe gắn máy, xe thô sơ, người đi bộ không được đi trên đường
      cao tốc". A vehicle surely banned from the expressway can't lawfully drive on it at any
      speed, so a speed claim for it fails (speed_violation/6 hook, cited r_expressway_entry).
    - R.415a, the vehicles allowed on the lanes (dev2 train_121). QCVN 41 D.16 a): R.415a shows
      "số lượng làn đường và loại xe được phép lưu thông trên từng làn đường". With no lane asked
      about, a motor vehicle listed on no lane of the board may not travel on the lanes it
      covers. D.16 d) limits the board to "làn đường cơ giới", so a non-motor vehicle missing
      from it may still use another lane: unknown. Pedestrians are not vehicles: not covered.
    - Two lane boards that disagree about a lane (dev2 train_516). A photo can't show which
      carriageway each board covers, so a lane closed by one board and open on another is
      unknown, not closed (lane_conflict/4, a check of lane_sign_checks/5 in speed.pl).

    No cuts outside leaf/1 helpers.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

% ---- expressway ban and speed

%  Only a vehicle the ban surely covers: for a broader class ("xe", motor_vehicle, the parser's
%  default) or a class art. 25.3 leaves open (three-wheelers), the speed signs decide as before.
expressway_speed_violation(Veh, S, Tz) :-
    zone_start(expressway, S, Tz),
    cite(r_expressway_entry),
    expressway_banned(Veh, true).

% ---- R.415a: vehicles on no lane of the board

lanes_by_vehicle_board(r415a).

leaf(board_specs(_, _)).
board_specs(S, Specs) :- findall(Sp, lane_vehicle(S, _, Sp), Specs), Specs \== [].

leaf(motor_lane_truth(_, _)).
%!  motor_lane_truth(+Veh, -T) is det.  true for a motor vehicle, false for a pedestrian (not a
%   vehicle), unknown otherwise (a non-motor vehicle may have its own lane, D.16 d).
motor_lane_truth(veh(VC, _), T) :-
    class_truth(motor_vehicle, VC, Tm),
    class_truth(vehicle, VC, Tv),
    (   Tm == true -> T = true
    ;   Tv == false -> T = false
    ;   T = unknown
    ).

board_forbids(Veh, S, T) :-
    scene_sign(S, Code),
    lanes_by_vehicle_board(Code),
    catalog_sign(Code, _, _, _),
    cite(r_lanes_by_vehicle),
    board_specs(S, Specs),
    any_spec_match(Specs, Veh, M),
    not3(M, T0),
    motor_lane_truth(Veh, Tm),
    and3([T0, Tm], T),
    T \== false.

board_clears(Veh, S, vehicle_on_a_lane) :-
    scene_sign(S, Code),
    lanes_by_vehicle_board(Code),
    catalog_sign(Code, _, _, _),
    cite(r_lanes_by_vehicle),
    board_specs(S, Specs),
    any_spec_match(Specs, Veh, true).
board_clears(Veh, S, vehicle_not_covered) :-
    scene_sign(S, Code),
    lanes_by_vehicle_board(Code),
    catalog_sign(Code, _, _, _),
    cite(r_lanes_by_vehicle),
    board_specs(_, _),
    motor_lane_truth(Veh, false).

% ---- two lane boards that disagree about a lane

leaf(lane_conflict(_, _, _, _)).
%!  lane_conflict(+S, +Lane, +Veh, -T) is det.  unknown when another lane sign has rows for Lane
%   and one of them may admit Veh; true otherwise.
lane_conflict(S, Lane, Veh, T) :-
    (   lane_vehicle(S2, Lane, _), S2 \== S,
        findall(Sp, lane_vehicle(S2, Lane, Sp), Specs),
        any_spec_match(Specs, Veh, M), M \== false
    ->  T = unknown
    ;   T = true
    ).
