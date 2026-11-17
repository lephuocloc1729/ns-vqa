/*  Phase 4.7 step 1d (owner, 2026-11-17: additive only): rules on scene v6's facts.

    - R.411 lane arrows (QCVN 41 D.13: "Biển có tác dụng bắt buộc người tham gia giao thông phải
      đi đúng làn đường đã được chỉ dẫn hướng phù hợp với hành trình của xe"): on a lane asked
      about, a direction the board's arrows don't show for that lane is forbidden.
    - Traffic lights (QCVN 41 art. 6): light_forbids/3.
    - Road markings (QCVN 41 G.1): marking_forbids/3.
    With no scene v6 fact, none of these rules has a solution, so no earlier answer changes.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

% ---------------------------------------------------------------- R.411 (D.13)

%!  r411_forbids(+Action, +Lane, -S, -T) is nondet.
r411_forbids(Action, Lane, S, true) :-
    lane_arrow_action(Action),
    scene_sign(S, Code),
    catalog_sign(Code, _, _, _),
    lane_arrow_board(Code),
    has_lane_arrows(S, Lane),
    \+ lane_direction(S, Lane, Action),
    cite(r_r411_lane_arrows).

%!  r411_clears(+Action, +Lane, -S, -Why) is nondet.
r411_clears(Action, Lane, S, direction_allowed) :-
    lane_arrow_action(Action),
    scene_sign(S, Code),
    lane_arrow_board(Code),
    lane_direction(S, Lane, Action),
    cite(r_r411_lane_arrows).

lane_arrow_action(go_straight).
lane_arrow_action(turn_left).
lane_arrow_action(turn_right).
lane_arrow_action(u_turn).

lane_arrow_board(r411).

leaf(has_lane_arrows(_, _)).
has_lane_arrows(S, Lane) :- lane_direction(S, Lane, _), !.

leaf(lane_arrows_read(_)).
%!  lane_arrows_read(+S): the board's arrows were read for some lane (the effect is then modelled).
lane_arrows_read(S) :- lane_direction(S, _, _), !.

% ---------------------------------------------------------------- lights (art. 6)

%!  light_forbids(+Action, +Veh, +PastStopLine, -T) is nondet.
%   One solution per round light facing the camera; arrow lights are checked first for their
%   own direction (6.4). PastStopLine: true | false | unknown (6.3.2).
light_forbids(_Action, Veh, _, false) :-                    % 27.4: priority vehicles on duty
    priority_exempt_speed(Veh), signal(vehicle, _, _, _).
light_forbids(Action, Veh, Past, T) :-
    \+ priority_exempt_speed(Veh),
    arrow_for(Action, Arrow),
    signal(vehicle, Colour, Arrow, _),
    cite(r_light_arrow),
    arrow_truth(Colour, Past, T).
light_forbids(Action, Veh, Past, T) :-
    \+ priority_exempt_speed(Veh),
    \+ ( arrow_for(Action, A), signal(vehicle, _, A, _) ),
    signal(vehicle, Colour, none, Flash),
    cite(r_light),
    round_truth(Colour, Flash, Past, T).

arrow_for(turn_left, left).
arrow_for(u_turn, left).          % 6.4.1 "Tín hiệu mũi tên cho phép rẽ trái thì đồng thời cho phép quay đầu"
arrow_for(go_straight, straight).
arrow_for(turn_right, right).

% 6.4.1 / 6.4.3: a green arrow lets the arrow's direction go; 6.4.4: a red arrow stops it.
arrow_truth(green, _, false).
arrow_truth(red, _, true).
arrow_truth(yellow, Past, T) :- yellow_truth(Past, T).
arrow_truth(off, _, unknown).

% 6.3.1 "Tín hiệu xanh: ... là được đi"; 6.3.3 "Tín hiệu đèn màu đỏ là cấm đi";
% 6.3.2 yellow: "phải dừng lại trước vạch dừng; trường hợp đang đi trên vạch dừng hoặc đã đi qua
% vạch dừng ... thì được đi tiếp"; flashing yellow: "được đi nhưng phải quan sát, giảm tốc độ".
round_truth(green, _, _, false).
round_truth(red, _, _, true).
round_truth(yellow, true, _, false).
round_truth(yellow, false, Past, T) :- yellow_truth(Past, T).
round_truth(off, _, _, unknown).

yellow_truth(true, false).
yellow_truth(false, true).
yellow_truth(unknown, unknown).

% ---------------------------------------------------------------- markings (G.1)

%!  marking_forbids(+Maneuver, +Lane, -T) is nondet.
%   Maneuver: cross_center (lấn sang làn ngược chiều, đè vạch tim đường) or change_lane (between
%   lanes of one direction; with Lane, only the line next to that lane). T true / false / unknown.
marking_forbids(cross_center, _, T) :-
    marking(center, Pattern, _, _),
    cite(r_marking_center),
    center_truth(Pattern, T).
marking_forbids(change_lane, Lane, T) :-
    marking(lane_line, Pattern, Lo, Hi),
    next_to(Lane, Lo, Hi),
    cite(r_marking_lane_line),
    lane_line_truth(Pattern, T).
marking_forbids(change_lane, _, true) :-
    marking(hatched, _, _, _),
    cite(r_marking_hatched).

next_to(Lane, _, _) :- \+ integer(Lane).
next_to(Lane, Lo, Hi) :- integer(Lane), ( Lane =:= Lo ; Lane =:= Hi ).

% G.1 1.1 "Xe được phép cắt qua"; 1.2 / 1.3 "xe không được lấn làn, không được đè lên vạch";
% 1.4 depends on the side the vehicle is on (unknown here).
center_truth(dashed, false).
center_truth(solid, true).
center_truth(double_solid, true).
center_truth(solid_dashed, unknown).
center_truth(dashed_solid, unknown).
center_truth(unknown, unknown).

% G.1 2.1 "xe được phép thực hiện việc chuyển làn đường qua vạch 2.1"; 2.2 "trường hợp không cho phép
% xe chuyển làn ... xe không được lấn làn, không được đè lên vạch"; 2.4 by side (unknown here).
lane_line_truth(dashed, false).
lane_line_truth(solid, true).
lane_line_truth(double_solid, true).
lane_line_truth(solid_dashed, unknown).
lane_line_truth(dashed_solid, unknown).
lane_line_truth(unknown, unknown).

%!  q_v6(+Goal3, -Out) is det.  Goal3 is light_forbids/4 or marking_forbids/3 with its truth last:
%   Out = _{verdict: no | unknown | yes | none, reasons: [...]} (no = forbidden).
q_v6(G, _{verdict:V, reasons:Rs}) :-
    findall(R-T, ( v6_goal(G, T, Goal), prove(Goal, P), proof_root(Goal, P, D),
                   reason_dict('', T, D, R) ), RTs),
    findall(R, member(R-_, RTs), Rs),
    findall(T, member(_-T, RTs), Ts),
    (   Ts == [] -> V = none
    ;   memberchk(true, Ts) -> V = no
    ;   memberchk(unknown, Ts) -> V = unknown
    ;   V = yes
    ).

v6_goal(light(A, Veh, Past), T, light_forbids(A, Veh, Past, T)).
v6_goal(marking(M, Lane), T, marking_forbids(M, Lane, T)).
