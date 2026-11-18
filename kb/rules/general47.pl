/*  Phase 4.7 step 1c (owner, 2026-11-17: additive only): general traffic rules of Law 36/2024
    that hold without a sign, asked through the `rule_permitted` intent (vqa/schemas.py).

    general_ban(+Action, +Place, -Rule): Law 36 forbids Action at Place for every vehicle.
    The places are the law's own lists; each fact quotes its point. A sign or traffic officer
    may lift some bans ("trừ những trường hợp tổ chức giao thông cho phép", 18.4 c; 15.4 "trừ khi
    có hiệu lệnh của người điều khiển giao thông hoặc chỉ dẫn của biển báo hiệu tạm thời"): a scene
    sign that marks the place as one where the action is permitted (permits_here/2, F6) makes the ban
    unknown, never false.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.
:- discontiguous general_ban/3.

% ---- Law 36 art. 14.6 "Không được vượt xe trong trường hợp sau đây"
general_ban(overtake, narrow_one_lane_bridge,   r_l36_overtaking).   % b) "Trên cầu hẹp có một làn đường"
general_ban(overtake, curve_limited_view,       r_l36_overtaking).   % c) "Đường cong có tầm nhìn bị hạn chế"
general_ban(overtake, hill_crest_limited_view,  r_l36_overtaking).   % d) "khu vực đỉnh dốc có tầm nhìn bị hạn chế"
general_ban(overtake, intersection,             r_l36_overtaking).   % đ) "Nơi đường giao nhau"
general_ban(overtake, railway_crossing,         r_l36_overtaking).   % đ) "đường bộ giao nhau cùng mức với đường sắt"
general_ban(overtake, pedestrian_crossing,      r_l36_overtaking).   % h) "Ở phần đường dành cho người đi bộ qua đường"
general_ban(overtake, tunnel,                   r_l36_overtaking).   % k) "Trong hầm đường bộ"

% ---- Law 36 art. 15.4 "Không được quay đầu xe ở ..."
general_ban(u_turn, pedestrian_crossing,  r_l36_u_turn).   % "phần đường dành cho người đi bộ qua đường"
general_ban(u_turn, bridge,               r_l36_u_turn).   % "trên cầu"
general_ban(u_turn, narrow_one_lane_bridge, r_l36_u_turn). % "trên cầu"
general_ban(u_turn, bridge_head,          r_l36_u_turn).   % "đầu cầu"
general_ban(u_turn, under_overpass,       r_l36_u_turn).   % "gầm cầu vượt"
general_ban(u_turn, ford,                 r_l36_u_turn).   % "ngầm"
general_ban(u_turn, railway_crossing,     r_l36_u_turn).   % "nơi đường bộ giao nhau cùng mức với đường sắt"
general_ban(u_turn, narrow_road,          r_l36_u_turn).   % "đường hẹp"
general_ban(u_turn, slope,                r_l36_u_turn).   % "đường dốc"
general_ban(u_turn, curve_limited_view,   r_l36_u_turn).   % "đoạn đường cong tầm nhìn bị che khuất"
general_ban(u_turn, expressway,           r_l36_u_turn).   % "trên đường cao tốc"
general_ban(u_turn, tunnel,               r_l36_u_turn).   % "trong hầm đường bộ"
general_ban(u_turn, one_way_road,         r_l36_u_turn).   % "trên đường một chiều"

% ---- Law 36 art. 18.4 "không được dừng xe, đỗ xe tại các vị trí sau đây"
general_ban(A, P, r_l36_stopping) :- g47_stop_or_park(A), stop_ban_place(P).
g47_stop_or_park(stop).
g47_stop_or_park(park).
stop_ban_place(one_way_road_left_side).   % a) "Bên trái đường một chiều"
stop_ban_place(curve_limited_view).       % b) "Trên đoạn đường cong ... mà tầm nhìn bị che khuất"
stop_ban_place(hill_crest_limited_view).  % b) "gần đầu dốc mà tầm nhìn bị che khuất"
stop_ban_place(bridge).                   % c) "Trên cầu, trừ những trường hợp tổ chức giao thông cho phép"
stop_ban_place(narrow_one_lane_bridge).   % c)
stop_ban_place(under_overpass).           % d) "Gầm cầu vượt, trừ những nơi cho phép dừng xe, đỗ xe"
stop_ban_place(pedestrian_crossing).      % g) "Trên phần đường dành cho người đi bộ qua đường"
stop_ban_place(intersection).             % h) "Nơi đường giao nhau và trong phạm vi 05 mét"
stop_ban_place(pickup_point).             % i) "Điểm đón, trả khách"
stop_ban_place(one_lane_width).           % l) "nơi phần đường có chiều rộng chỉ đủ cho một làn xe cơ giới"
stop_ban_place(railway_safety_zone).      % m) "Trong phạm vi an toàn của đường sắt"
stop_ban_place(bus_lane).                 % o) "Trên đường dành riêng cho xe buýt"

% ---- Law 36 art. 25.1 c) "Không được cho xe chạy ở làn dừng xe khẩn cấp và phần lề đường"
general_ban(enter, emergency_lane, r_l36_expressway).

% ---- Law 36 art. 16.2 (owner, 2026-11-18): "Không được lùi xe ở đường một chiều, khu vực cấm dừng, trên
% phần đường dành cho người đi bộ qua đường, nơi đường bộ giao nhau, đường bộ giao nhau cùng mức với đường
% sắt, nơi tầm nhìn bị che khuất, trong hầm đường bộ, trên đường cao tốc."
general_ban(reverse, one_way_road,        r_l36_reversing).
general_ban(reverse, no_stopping_zone,    r_l36_reversing).   % "khu vực cấm dừng"
general_ban(reverse, pedestrian_crossing, r_l36_reversing).
general_ban(reverse, intersection,        r_l36_reversing).
general_ban(reverse, railway_crossing,    r_l36_reversing).
general_ban(reverse, limited_view,        r_l36_reversing).   % "nơi tầm nhìn bị che khuất"
general_ban(reverse, curve_limited_view,  r_l36_reversing).   % a curve with its view blocked is such a place
general_ban(reverse, hill_crest_limited_view, r_l36_reversing).
general_ban(reverse, tunnel,              r_l36_reversing).
general_ban(reverse, expressway,          r_l36_reversing).

%!  general_forbids(+Action, +Veh, +Place, -T) is nondet.
%   T = true, or unknown when a scene sign permits the action at this place (the law's own
%   exceptions; see the header).
general_forbids(Action, _Veh, Place, T) :-
    general_ban(Action, Place, Rule),
    cite(Rule),
    (   lifted_by_sign(Action) -> T = unknown ; T = true ).

leaf(lifted_by_sign(_)).
lifted_by_sign(Action) :- scene_sign(_, Code), permits_here(Code, Action), !.

% ---- Law 36 art. 26.2 (owner, 2026-11-18): "Không dừng xe, đỗ xe trong hầm đường bộ; trường hợp gặp sự cố
% kỹ thuật hoặc bất khả kháng khác buộc phải dừng xe, đỗ xe, người lái xe ... phải đưa xe vào vị trí dừng xe,
% đỗ xe khẩn cấp". Same pattern as the emergency lane (25.2): Reason = breakdown | other | unknown.
tunnel_stop(Reason, T) :-
    cite(r_l36_tunnel),
    (   Reason == breakdown -> T = false
    ;   Reason == other -> T = true
    ;   T = unknown
    ).

% ---- Law 36 art. 25.2: stopping in the emergency lane only on a breakdown or force majeure
% ("trường hợp gặp sự cố kỹ thuật hoặc bất khả kháng khác buộc phải dừng xe, đỗ xe thì được dừng
% xe, đỗ xe ở làn dừng khẩn cấp"). Reason = breakdown | other | unknown.
emergency_stop(Reason, T) :-
    cite(r_l36_expressway),
    (   Reason == breakdown -> T = false
    ;   Reason == other -> T = true
    ;   T = unknown
    ).

% ---- Law 36 art. 13.3: "xe thô sơ phải đi trên làn đường bên phải trong cùng"
%!  rudimentary_lane(+Veh, +Lane, +N, -T): T = true when Veh is rudimentary and Lane is not lane N
%   (the rightmost of N lanes), so the law forbids driving there.
rudimentary_lane(veh(C, _), Lane, N, T) :-
    subclass_of(C, rudimentary),
    integer(Lane), integer(N),
    cite(r_l36_lane_use),
    (   Lane =:= N -> T = false ; T = true ).

% ---- Law 36 art. 27.4: priority vehicles on duty "không bị hạn chế tốc độ; được phép đi không phụ
% thuộc vào tín hiệu đèn giao thông"
priority_exempt_speed(veh(_, Attrs)) :-
    memberchk(a(priority, true), Attrs),
    cite(r_l36_priority).

% ---- Circular 38/2024 art. 7 (interpretation r_c38_outside): maximum speeds outside residential
% areas, by vehicle group and road (divided or one-way with two or more lanes / undivided two-way).
%!  c38_outside_limit(+Veh, +Divided, -Kmh) is semidet.
c38_outside_limit(veh(C, Attrs), Divided, Kmh) :-
    c38_group(C, Attrs, G),
    c38_outside(G, Divided, Kmh),
    cite(r_c38_outside).

c38_outside(g1, true, 90).  c38_outside(g1, false, 80).
c38_outside(g2, true, 80).  c38_outside(g2, false, 70).
c38_outside(g3, true, 70).  c38_outside(g3, false, 60).
c38_outside(g4, true, 60).  c38_outside(g4, false, 50).   % kept for the review: no class reaches g4 yet

leaf(c38_group(_, _, _)).
%  Owner's check (2026-11-17): art. 7's groups as believed, from memory (interpretation):
%  g1 "xe ô tô chở người đến 28 chỗ (trừ xe buýt); ô tô tải có khối lượng hàng chuyên chở cho phép
%     tham gia giao thông đến 3,5 tấn";
%  g2 "xe ô tô chở người trên 28 chỗ (trừ xe buýt); ô tô tải có khối lượng hàng chuyên chở ... trên
%     3,5 tấn (trừ ô tô xi téc ...)";
%  g3 "ô tô buýt; ô tô đầu kéo kéo sơ mi rơ moóc; xe mô tô; ô tô chuyên dùng (trừ ô tô trộn vữa ...)";
%  g4 "ô tô kéo rơ moóc; ô tô kéo xe khác; ô tô trộn vữa, trộn bê tông lưu động; ô tô xi téc".
%  The truck test is the PAYLOAD (load_t), not the gross mass. A gross mass up to 3.5 t still
%  bounds the payload (load <= gross, B.15), so it gives g1; a larger gross mass says nothing.
%  A coach (xe khách) needs its seat count; `bus` (any passenger vehicle, maybe a coach) and
%  g4's vehicles (no class in the ontology; a truck over 3.5 t might be a tanker, g4) are not
%  placed, so the limit stays unknown for them. A truck over 3.5 t payload is placed in g2,
%  which assumes it is not a tanker: a question naming a tanker has no class to say so.
c38_group(C, _, g1) :- memberchk(C, [passenger_car, taxi]), !.
c38_group(coach, Attrs, G) :-
    memberchk(a(seats, S), Attrs), !,
    cmp_truth(gt, S, 28, T),
    (   T == true -> G = g2 ; T == false -> G = g1 ).
c38_group(C, _, g3) :- memberchk(C, [city_bus, motorbike, motorcycle, sidecar]), !.
c38_group(truck, Attrs, G) :-
    (   memberchk(a(load_t, L), Attrs)
    ->  cmp_truth(gt, L, 3.5, T),
        (   T == true -> G = g2 ; T == false -> G = g1 )
    ;   memberchk(a(gross_t, W), Attrs),
        cmp_truth(le, W, 3.5, true),
        G = g1
    ), !.

%!  q_general(+Action, +Veh, +Place, -Out) is det.
q_general(Action, Veh, Place, _{verdict:V, reasons:Rs}) :-
    findall(R-T, ( prove(general_forbids(Action, Veh, Place, T), P),
                   proof_root(general_forbids(Action, Veh, Place, T), P, D),
                   reason_dict('', T, D, R) ), RTs),
    findall(R, member(R-_, RTs), Rs),
    findall(T, member(_-T, RTs), Ts),
    (   memberchk(true, Ts) -> V = no
    ;   memberchk(unknown, Ts) -> V = unknown
    ;   V = none
    ).

%!  q_goal(+Goal, -Out) is det.  Proves a phase-4.7 helper goal whose last argument is a truth
%   value (or that succeeds), with its proof: Out = _{ok:Bool, truth:T, proof:D}.
q_goal(G, _{ok:true, proof:D}) :- prove(G, P), proof_root(G, P, D), !.
q_goal(_, _{ok:false, proof:null}).

%!  q_c38(+Veh, +Divided, -Out) is det.  Out = _{limit:Kmh | none, proof:D}.
q_c38(Veh, Div, _{limit:K, proof:D}) :-
    prove(c38_outside_limit(Veh, Div, K), P), proof_root(c38_outside_limit(Veh, Div, K), P, D), !.
q_c38(_, _, _{limit:none, proof:null}).
