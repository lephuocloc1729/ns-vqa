/*  Rule family: zones set by signs, places a sign marks, and default speeds by road type
    (phase 4.5 stage A; owner, 2026-11-17).

    - Expressways (F4): IE.452 / IE.451b start one, IE.453b/c end it (KB-4, an
      interpretation). On it, Law 36/2024 art. 25.3 bans some vehicles and art. 25.2 allows
      stopping and parking only where permitted.
    - Residential areas (F4): R.420 starts one, R.421 ends it (QCVN 41 D.17, D.18).
    - Default speeds by road type (Circular 38/2024; interpretations r_c38_*, owner's
      exception): they apply only when no posted speed sign of the same kind is in the scene.
    - Places (F6): I.409 (U-turns allowed here), I.408 (parking allowed here); I.434a marks a
      pick-up point, where vehicles other than buses may not stop or park (Law 36 art. 18.4 i).
    - KB-1 / KB-2: R.302 and R.303 don't ban a direction; the proof of a "yes" names them.

    Hooks, called from prohibitions.pl (forbids/5, clears/5) and speed.pl
    (speed_violation/6, speed_clears/6, limit_candidate/6). No cuts outside leaf/1 helpers.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.
:- discontiguous zone_forbids/5, zone_clears/5.

% --------------------------------------------------------------------------
% Zones
% --------------------------------------------------------------------------

%!  zone_start(+Kind, -S, -T) is nondet.
%   Sign S starts a zone of Kind. T is true, or unknown when a sign ending that kind of zone
%   is in the scene too: a still photo can't show which side of it we are on.
zone_start(Kind, S, T) :-
    scene_sign(S, Code),
    zone_sign(Code, Kind, start),
    zone_cite(Kind),
    zone_end_truth(Kind, T).

zone_cite(expressway) :- cite(r_kb4_expressway_zone).
zone_cite(residential) :- cite(r_residential_zone).

leaf(zone_end_truth(_, _)).
zone_end_truth(Kind, T) :- ( scene_sign(_, C), zone_sign(C, Kind, end) -> T = unknown ; T = true ).

leaf(expressway_banned(_, _)).
%!  expressway_banned(+Veh, -T) is det.  Law 36/2024 art. 25.3: "xe mô tô, xe gắn máy, các loại
%   xe tương tự xe mô tô, xe gắn máy, xe thô sơ, người đi bộ không được đi trên đường cao tốc".
%   Slow special machines ("có tốc độ thiết kế nhỏ hơn tốc độ tối thiểu") and three-wheelers
%   (whether "tương tự xe mô tô") depend on facts a photo lacks, so they are unknown.
expressway_banned(veh(VC, _), T) :-
    findall(Ti, ( member(B, [motorbike, rudimentary, pedestrian]), class_truth(B, VC, Ti) ), T1),
    findall(Ti, ( member(B, [special_machine, motor_tricycle]), class_truth(B, VC, T0),
                  ( T0 == false -> Ti = false ; Ti = unknown ) ), T2),
    append(T1, T2, Ts),
    or3(Ts, T).

stop_or_park(stop).
stop_or_park(park).

leaf(not_city_bus(_, _)).
not_city_bus(veh(VC, _), T) :- class_truth(city_bus, VC, T0), not3(T0, T).

% ---- what a zone or a place forbids

zone_forbids(enter, Veh, _Ctx, S, T) :-
    zone_start(expressway, S, Tz),
    cite(r_expressway_entry),
    expressway_banned(Veh, Tb),
    Tb \== false,
    and3([Tz, Tb], T).

zone_forbids(Action, _Veh, _Ctx, S, T) :-
    stop_or_park(Action),
    zone_start(expressway, S, T),
    cite(r_expressway_stop).

zone_forbids(Action, Veh, _Ctx, S, T) :-
    stop_or_park(Action),
    scene_sign(S, Code),
    conduct(Code, pickup_point),
    catalog_sign(Code, _, _, _),
    cite(r_pickup_point),
    not_city_bus(Veh, T),
    T \== false.

% ---- why a zone or a place doesn't forbid (the proof of a "yes")

zone_clears(enter, Veh, _Ctx, S, vehicle_not_covered) :-
    zone_start(expressway, S, _),
    cite(r_expressway_entry),
    expressway_banned(Veh, false).

zone_clears(Action, Veh, _Ctx, S, vehicle_not_covered) :-
    stop_or_park(Action),
    scene_sign(S, Code),
    conduct(Code, pickup_point),
    catalog_sign(Code, _, _, _),
    cite(r_pickup_point),
    not_city_bus(Veh, false).

zone_clears(Action, _Veh, _Ctx, S, permitted_here) :-
    scene_sign(S, Code),
    permits_here(Code, Action),
    catalog_sign(Code, _, _, _).

zone_clears(Action, _Veh, _Ctx, S, pass_side_only) :-
    direction_action(Action),
    scene_sign(S, Code),
    pass_side(Code, _),
    catalog_sign(Code, _, _, _),
    cite(r_kb1_pass_side).

zone_clears(Action, _Veh, _Ctx, S, yield_only) :-
    direction_action(Action),
    scene_sign(S, Code),
    yield_from(Code, _),
    catalog_sign(Code, _, _, _),
    cite(r_kb2_roundabout).

% --------------------------------------------------------------------------
% Default speeds by road type (Circular 38/2024, interpretations)
% --------------------------------------------------------------------------

leaf(posted_max_sign).
posted_max_sign :- scene_sign(_, C), ( max_speed_for(C, _) ; lane_board(C) ), !.
leaf(posted_min_sign).
posted_min_sign :- scene_sign(_, C), ( min_speed_for(C, _) ; lane_board(C) ), !.

leaf(unread_truth(_)).
%!  unread_truth(-T) is det.  unknown when the scene has a sign that couldn't be read (UNKNOWN or
%   not in the catalog): it might be the posted limit, so a road-type default can't be relied on.
unread_truth(T) :- ( unread_sign(_) -> T = unknown ; T = true ).

leaf(motor_truth(_, _)).
motor_truth(veh(VC, _), T) :- class_truth(motor_vehicle, VC, T).

leaf(moped_truth(_, _)).
moped_truth(veh(VC, _), T) :- class_truth(moped, VC, T).

leaf(non_moped_motor_truth(_, _)).
%  Motor vehicles other than mopeds (mopeds have their own limit, r_c38_moped).
non_moped_motor_truth(veh(VC, _), T) :-
    class_truth(motor_vehicle, VC, T1),
    class_truth(moped, VC, T2),
    not3(T2, N2),
    and3([T1, N2], T).

leaf(residential_exceeds(_, _)).
%!  residential_exceeds(+Speed, -T) is det.  60 km/h on a divided road, 50 on an undivided one;
%   when the scene doesn't say, a speed over 60 exceeds both, one over 50 may exceed.
residential_exceeds(Speed, T) :-
    (   road_divided(true) -> cmp_truth(gt, Speed, 60, T)
    ;   road_divided(false) -> cmp_truth(gt, Speed, 50, T)
    ;   Speed > 60 -> T = true
    ;   Speed > 50 -> T = unknown
    ;   T = false
    ).

leaf(residential_max(_)).
residential_max(60) :- road_divided(true), !.
residential_max(50) :- road_divided(false).

%!  default_violation(+Veh, +Speed, +Ctx, -S, -T) is nondet.
default_violation(Veh, Speed, _Ctx, S, T) :-
    \+ posted_max_sign,
    zone_start(expressway, S, Tz),
    cite(r_c38_expressway),
    Speed > 120,
    motor_truth(Veh, Tm), Tm \== false,
    unread_truth(Tu),
    and3([Tz, Tm, Tu], T).
default_violation(Veh, Speed, _Ctx, S, T) :-
    \+ posted_min_sign,
    zone_start(expressway, S, Tz),
    cite(r_c38_expressway),
    Speed < 60,
    motor_truth(Veh, Tm), Tm \== false,
    unread_truth(Tu),
    and3([Tz, Tm, Tu], T).
default_violation(Veh, Speed, _Ctx, S, T) :-
    \+ posted_max_sign,
    zone_start(residential, S, Tz),
    cite(r_c38_residential),
    non_moped_motor_truth(Veh, Tm), Tm \== false,
    residential_exceeds(Speed, Te), Te \== false,
    unread_truth(Tu),
    and3([Tz, Tm, Te, Tu], T).
default_violation(Veh, Speed, _Ctx, S, T) :-
    \+ posted_max_sign,
    zone_start(residential, S, Tz),
    cite(r_c38_moped),
    Speed > 40,
    moped_truth(Veh, Tm), Tm \== false,
    unread_truth(Tu),
    and3([Tz, Tm, Tu], T).

%!  default_clears(+Veh, +Speed, +Ctx, -S, -Why) is nondet.  A road-type default applies and
%   is not broken.
default_clears(Veh, Speed, Ctx, S, within_limit) :-
    \+ posted_max_sign,
    unread_truth(true),
    zone_start(Kind, S, _),
    default_cite(Kind),
    motor_truth(Veh, Tm), Tm \== false,
    \+ default_violation(Veh, Speed, Ctx, S, _).

default_cite(expressway) :- cite(r_c38_expressway).
default_cite(residential) :- cite(r_c38_residential).

%!  default_limit_value(+Veh, +Ctx, +Kind, -S, -V, -T) is nondet.  For speed_limit queries.
%   Not when a sign is unread (it might be the posted limit). The moped limit (r_c38_moped) is
%   left out here: for a broader class ("xe máy") it would name a limit only mopeds have.
default_limit_value(Veh, _Ctx, max, S, 120, T) :-
    \+ posted_max_sign,
    unread_truth(true),
    zone_start(expressway, S, Tz),
    cite(r_c38_expressway),
    motor_truth(Veh, Tm), Tm \== false,
    and3([Tz, Tm], T).
default_limit_value(Veh, _Ctx, min, S, 60, T) :-
    \+ posted_min_sign,
    unread_truth(true),
    zone_start(expressway, S, Tz),
    cite(r_c38_expressway),
    motor_truth(Veh, Tm), Tm \== false,
    and3([Tz, Tm], T).
default_limit_value(Veh, _Ctx, max, S, V, T) :-
    \+ posted_max_sign,
    unread_truth(true),
    zone_start(residential, S, Tz),
    cite(r_c38_residential),
    residential_max(V),
    non_moped_motor_truth(Veh, Tm), Tm \== false,
    and3([Tz, Tm], T).
