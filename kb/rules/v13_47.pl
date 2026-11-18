/*  Parser v13 (owner, 2026-11-18: additive only): rules for the new question types. Each rule
    quotes the law_db text it follows. With no question asking for them, none of these rules is
    called, so no earlier answer changes. The one exception is light_overrides_sign/1, used by
    rule_permitted only when a green arrow light for the very action is read (QCVN 41 art. 4.1).

    - Traffic officer's gestures (Law 36 art. 11.3): officer_says/3, officer_forbids/4.
    - Which signalling means wins (Law 36 art. 11.2 and 11.12; QCVN 41 art. 4.1 and 4.2):
      precedence_winner/3.
    - Who yields at an intersection (Law 36 art. 22; QCVN 41 D.1, C.7, C.8, E.1): row_basis/3,
      must_yield/4. The signs in the photo are taken as the ones on the driver's approach (the
      photo is the driver's view, as for every other sign question); the owner reviews this.
    - Vehicle classes (Law 36 art. 34, kb/ontology.pl): vehicle_class_truth/3.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

% ---------------------------------------------------------------- Law 36 art. 11.3: the officer
% a) "Tay bên phải giơ thẳng đứng để báo hiệu cho người tham gia giao thông đường bộ ở tất cả các
%    hướng phải dừng lại"
officer_says(right_arm_up, front, stop).
officer_says(right_arm_up, back, stop).
officer_says(right_arm_up, left, stop).
officer_says(right_arm_up, right, stop).
% b) "Hai tay hoặc một tay dang ngang để báo hiệu cho người tham gia giao thông đường bộ ở phía
%    trước và ở phía sau người điều khiển giao thông phải dừng lại; người tham gia giao thông
%    đường bộ ở phía bên phải và bên trái người điều khiển giao thông được đi"
officer_says(arms_sideways, front, stop).
officer_says(arms_sideways, back, stop).
officer_says(arms_sideways, left, go).
officer_says(arms_sideways, right, go).
% c) "Tay bên phải giơ về phía trước để báo hiệu cho người tham gia giao thông đường bộ ở phía
%    sau và bên phải người điều khiển giao thông phải dừng lại; người tham gia giao thông đường
%    bộ ở phía trước người điều khiển giao thông được rẽ phải; người tham gia giao thông đường bộ
%    ở phía bên trái người điều khiển giao thông được đi tất cả các hướng"
officer_says(right_arm_forward, back, stop).
officer_says(right_arm_forward, right, stop).
officer_says(right_arm_forward, front, turn_right_only).
officer_says(right_arm_forward, left, all_directions).

%!  officer_forbids(+Gesture, +Side, +Action, -T) is det.  Side = unknown when the question does
%   not say where the driver is; only the all-directions stop (a) is decided then.
officer_forbids(G, Side, A, T) :-
    cite(r_l36_officer),
    (   Side == unknown
    ->  (   G == right_arm_up -> officer_truth(stop, A, T) ; T = unknown )
    ;   officer_says(G, Side, W),
        officer_truth(W, A, T)
    ).

officer_moving(enter). officer_moving(go_straight). officer_moving(turn_left).
officer_moving(turn_right). officer_moving(u_turn).

officer_truth(stop, A, T) :-
    (   A == stop -> T = false ; officer_moving(A) -> T = true ; T = unknown ).
officer_truth(all_directions, A, T) :-
    (   officer_moving(A) -> T = false ; T = unknown ).
% "được đi" does not say which directions: going on is allowed, a turn is not decided
officer_truth(go, A, T) :-
    (   memberchk(A, [enter, go_straight]) -> T = false ; T = unknown ).
% "được rẽ phải": read as the only move allowed (interpretation r_officer_right_turn_only)
officer_truth(turn_right_only, A, T) :-
    (   A == turn_right -> T = false
    ;   officer_moving(A) -> cite(r_officer_right_turn_only), T = true
    ;   T = unknown
    ).

% ---------------------------------------------------------------- which signalling means wins
% Law 36 art. 11.2 "phải chấp hành báo hiệu đường bộ theo thứ tự ưu tiên từ trên xuống dưới như
% sau: a) Hiệu lệnh của người điều khiển giao thông; b) Tín hiệu đèn giao thông; c) Biển báo hiệu
% đường bộ; d) Vạch kẻ đường và các dấu hiệu khác trên mặt đường; đ) Cọc tiêu, tường bảo vệ, rào
% chắn ...; e) Thiết bị âm thanh báo hiệu đường bộ" (the same list: QCVN 41 art. 4.1).
signal_rank(officer, 1).
signal_rank(light, 2).
signal_rank(sign, 3).
signal_rank(temporary_sign, 3).
signal_rank(permanent_sign, 3).
signal_rank(marking, 4).
signal_rank(roadside_device, 5).
signal_rank(sound_device, 6).

%!  precedence_winner(+A, +B, -W) is det.  W = A, B, or unknown (e.g. a sign against a temporary
%   sign: the first may be either kind).
% 11.12 "Khi ở một vị trí vừa có biển báo hiệu đặt cố định vừa có biển báo hiệu tạm thời mà hai
% biển có ý nghĩa khác nhau, người tham gia giao thông đường bộ phải chấp hành hiệu lệnh của biển
% báo hiệu tạm thời" (QCVN 41 art. 4.2).
precedence_winner(A, B, W) :-
    (   A == temporary_sign, B == permanent_sign -> cite(r_l36_temporary_sign), cite(r_qcvn_signal_order), W = A
    ;   A == permanent_sign, B == temporary_sign -> cite(r_l36_temporary_sign), cite(r_qcvn_signal_order), W = B
    ;   signal_rank(A, RA), signal_rank(B, RB), RA =\= RB
    ->  cite(r_l36_signal_order), cite(r_qcvn_signal_order), ( RA < RB -> W = A ; W = B )
    ;   W = unknown
    ).

%!  precedence_truth(+Winner, +Over, -T) is det.
precedence_truth(Winner, Over, T) :-
    precedence_winner(Winner, Over, W),
    (   W == Winner -> T = true ; W == Over -> T = false ; T = unknown ).

%!  light_overrides_sign(+Action) is semidet.  A green arrow light for this very action is read:
%   it says go where a sign says no, and the light comes first (11.2 b before c). A round green
%   light does not name the direction, so it never overrides a sign that bans a turn.
light_overrides_sign(Action) :-
    arrow_for(Action, Arrow),
    signal(vehicle, green, Arrow, _),
    cite(r_l36_signal_order), cite(r_qcvn_signal_order).

% ---------------------------------------------------------------- who yields at the intersection
% D.1 c) R.122 "Biển có hiệu lực bắt buộc người tham gia giao thông trên đường không ưu tiên phải
%   nhường đường"; C.8 b) "Các xe đi trên đường có đặt biển số W.208 phải nhường đường cho xe đi trên
%   đường ưu tiên khi qua nơi giao nhau"
row_yield_sign(r122).
row_yield_sign(w208).
% C.7 b) W.207 "Các xe đi trên đường có đặt biển này được quyền ưu tiên qua nơi giao nhau";
% E.1 b) I.401 "phương tiện được quyền ưu tiên đi qua nơi giao nhau không có điều khiển giao thông.
%   Phương tiện trên đường khác nhập vào hay cắt ngang qua phải nhường đường"
row_priority_sign(i401).
row_priority_sign(w207_a_b_c_d_e_f_g_h_i_k_l).
row_roundabout_sign(r303).
row_roundabout_sign(w206).

leaf(row_signs(_, _)).
row_signs(Ys, Ps) :-
    findall(C, ( scene_sign(_, C), row_yield_sign(C) ), Ys0), sort(Ys0, Ys),
    findall(C, ( scene_sign(_, C), row_priority_sign(C) ), Ps0), sort(Ps0, Ps).

leaf(row_light_read).
row_light_read :- signal(vehicle, C, _, _), C \== off, !.

leaf(row_roundabout_seen).
row_roundabout_seen :- scene_sign(_, C), row_roundabout_sign(C), !.

%!  row_basis(+MyRoad, +Roundabout, -B) is det.  MyRoad = main | branch | unknown; Roundabout =
%   true | false | unknown. B = signal | conflict | yield_sign(C) | priority_sign(C) | branch |
%   main | roundabout | equal.
row_basis(My, Round, B) :-
    (   row_light_read
    ->  cite(r_priority_road_controlled), B = signal      % E.1 b) "Nếu ở chỗ giao nhau có điều
                                                          % khiển giao thông thì nguyên tắc chạy xe
                                                          % ưu tiên hết tác dụng"
    ;   row_signs(Ys, Ps),
        (   Ys \== [], Ps \== [] -> B = conflict
        ;   Ys = [C|_]
        ->  catalog_sign(C, _, _, _), cite(r_l36_yield_main),
            ( My == main -> B = conflict ; B = yield_sign(C) )
        ;   Ps = [C|_]
        ->  catalog_sign(C, _, _, _), cite(r_l36_yield_main),
            ( My == branch -> B = conflict ; B = priority_sign(C) )
        ;   ( Round == true ; Round \== false, row_roundabout_seen )
        ->  cite(r_l36_yield_roundabout), B = roundabout
        ;   My == branch -> cite(r_l36_yield_main), B = branch
        ;   My == main -> cite(r_l36_yield_main), B = main
        ;   cite(r_l36_yield_right), B = equal
        )
    ).

%!  must_yield(+OtherFrom, +MyRoad, +Roundabout, -T) is det.  OtherFrom = right | left |
%   main_road | branch_road | cross_road | unknown.
% 22.1 "xe đi từ đường không ưu tiên hoặc đường nhánh phải nhường đường cho xe đi trên đường ưu tiên
%   hoặc đường chính từ bất kỳ hướng nào tới"; 22.2 "Tại nơi đường giao nhau không có báo hiệu đi
%   theo vòng xuyến, phải nhường đường cho xe đi đến từ bên phải"; 22.3 "Tại nơi đường giao nhau có
%   báo hiệu đi theo vòng xuyến, phải nhường đường cho xe đi đến từ bên trái".
must_yield(O, My, Round, T) :-
    row_basis(My, Round, B),
    yield_truth(B, O, T).

yield_truth(signal, _, unknown).
yield_truth(conflict, _, unknown).
yield_truth(yield_sign(_), O, T) :- yield_on_minor(O, T).
yield_truth(branch, O, T) :- yield_on_minor(O, T).
yield_truth(priority_sign(_), O, T) :- yield_on_major(O, T).
yield_truth(main, O, T) :- yield_on_major(O, T).
yield_truth(roundabout, O, T) :-
    (   O == left -> T = true ; O == right -> T = false ; T = unknown ).
yield_truth(equal, O, T) :-
    (   O == right -> T = true ; O == left -> T = false ; T = unknown ).

% on the minor road: the cross traffic is on the major road ("từ bất kỳ hướng nào tới"); another
% minor-road vehicle is not decided by 22.1
yield_on_minor(O, T) :-
    (   memberchk(O, [right, left, main_road, cross_road]) -> T = true ; T = unknown ).
% on the major road: the others yield (only priority vehicles keep their right, art. 27)
yield_on_major(O, T) :-
    (   O == main_road -> T = unknown ; T = false ).

% ---------------------------------------------------------------- Law 36 art. 34: vehicle classes
% 34.1 g) "Xe gắn máy là xe có hai hoặc ba bánh chạy bằng động cơ ..., có vận tốc thiết kế không lớn
% hơn 50 km/h; nếu động cơ dẫn động là động cơ nhiệt thì dung tích làm việc hoặc dung tích tương
% đương không lớn hơn 50 cm3; nếu động cơ dẫn động là động cơ điện thì công suất của động cơ không
% lớn hơn 04 kW"; 34.1 e) "Xe mô tô gồm: xe có hai hoặc ba bánh chạy bằng động cơ ..., trừ xe gắn máy".

%!  vehicle_class_truth(+Veh, +Target, -T) is det.
vehicle_class_truth(veh(C, Attrs), Target, T) :-
    cite(r_l36_vehicle_classes),
    (   subclass_of(C, Target) -> T = true
    ;   C == motorbike, memberchk(Target, [moped, motorcycle])
    ->  art34_moped_truth(Attrs, M),
        ( Target == moped -> T = M ; not3(M, T) )
    ;   subclass_of(Target, C) -> T = unknown          % the question names a broader class
    ;   T = false
    ).

art34_moped_truth(Attrs, T) :-
    art34_le(Attrs, design_speed_kmh, 50, Ts),
    (   memberchk(a(engine_cc, _), Attrs) -> art34_le(Attrs, engine_cc, 50, Te)
    ;   memberchk(a(motor_kw, _), Attrs) -> art34_le(Attrs, motor_kw, 4, Te)
    ;   Te = unknown
    ),
    and3([Ts, Te], T).

art34_le(Attrs, A, Max, T) :-
    (   memberchk(a(A, V), Attrs) -> cmp_truth(le, V, Max, T) ; T = unknown ).

leaf(vehicle_ancestors(_, _)).
vehicle_ancestors(C, L) :- findall(S, subclass_of(C, S), L).

% ---------------------------------------------------------------- entry points (Python)
%!  q_truth(+Goal, -Out) is det.  Goal is one of the predicates above without its last (truth)
%   argument: Out = _{truth: true | false | unknown, proof: D}.
q_truth(G, _{truth:T, proof:D}) :-
    G =.. L0, append(L0, [T], L1), G1 =.. L1,
    prove(G1, P), proof_root(G1, P, D), !.
q_truth(_, _{truth:unknown, proof:null}).

%!  q_row_basis(+My, +Round, -Out) is det.  Out = _{basis: Text, proof: D}.
q_row_basis(My, Round, _{basis:S, proof:D}) :-
    prove(row_basis(My, Round, B), P), proof_root(row_basis(My, Round, B), P, D),
    term_string(B, S), !.

%!  q_officer_says(+Gesture, -Out) is det.  Out = _{rows: [_{side:S, says:W}, ...]}.
q_officer_says(G, _{rows:Rows, proof:D}) :-
    findall(_{side:S, says:W}, officer_says(G, S, W), Rows),
    prove(cite(r_l36_officer), P), proof_root(cite(r_l36_officer), P, D).

%!  q_vehicle_ancestors(+Class, -Out) is det.
q_vehicle_ancestors(C, _{classes:L}) :- vehicle_ancestors(C, L).
