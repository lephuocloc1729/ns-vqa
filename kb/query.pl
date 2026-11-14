/*  Top-level queries called from Python (vqa/reasoning/engine.py).

    Each q_* returns a dict with
      verdict  yes | no | unknown
      reasons  signs that go against the claim (truth true or unknown), with proofs
      clears   signs that concern the question but do not go against it, each
               with the failed check (why) and its proof

    Any true reason decides; otherwise any unknown reason makes the verdict
    unknown. The combination is closed-world over the signs in the scene. When
    no sign concerns the question, `clears` lists the restricting signs that are
    about something else; when there are none, one entry says so.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

%!  reasons(:Template, -Reasons:list(dict), -Truths:list, -Signs:list) is det.
%   Template = S-T-Goal. Keeps the strongest reason per sign (true over unknown).
reasons(S-T-Goal, Reasons, Truths, Signs) :-
    findall(S-T-D, ( prove(Goal, P), proof_root(Goal, P, D) ), Raw),
    best_per_sign(Raw, Best),
    findall(R, ( member(S1-T1-D1, Best), reason_dict(S1, T1, D1, R) ), Reasons),
    findall(T1, member(_-T1-_, Best), Truths),
    findall(S1, member(S1-_-_, Best), Signs).

best_per_sign(Raw, Best) :-
    findall(S, member(S-_-_, Raw), Ss0), sort(Ss0, Ss),
    findall(S-T-D, ( member(S, Ss),
                     (   memberchk(S-true-D, Raw) -> T = true
                     ;   memberchk(S-unknown-D, Raw), T = unknown ) ), Best).

reason_dict(S, T, D, _{sign_id:SS, truth:TS, proof:D}) :-
    atom_string(S, SS), atom_string(T, TS).

%!  verdict_against(+Truths, -Verdict) is det.  Truths of reasons *against* the claim.
verdict_against(Ts, no)      :- memberchk(true, Ts), !.
verdict_against(Ts, unknown) :- memberchk(unknown, Ts), !.
verdict_against(_, yes).

%!  clears(+Groups, +Exclude, -Dicts) is det.
%   Groups: list of groups, each a list of S-Why-Goal templates. Groups are tried
%   in order and the first that yields anything is used. One entry per sign,
%   skipping signs in Exclude (they go against the claim).
clears([], Exclude, Dicts) :-
    G = (\+ restricting_scene_sign(_)),
    (   Exclude == [], prove(G, P)
    ->  proof_root(G, P, D),
        Dicts = [_{sign_id:"", truth:"false", why:"no_restricting_sign", proof:D}]
    ;   Dicts = []
    ).
clears([Group|More], Exclude, Dicts) :-
    findall(S-W-D, ( member(S-W-Goal, Group),
                     prove(Goal, P), \+ memberchk(S, Exclude),
                     proof_root(Goal, P, D) ), Raw),
    first_per_sign(Raw, Firsts),
    (   Firsts == []
    ->  clears(More, Exclude, Dicts)
    ;   findall(C, ( member(S1-W1-D1, Firsts), clear_dict(S1, W1, D1, C) ), Dicts)
    ).

first_per_sign(Raw, Firsts) :-
    findall(S, member(S-_-_, Raw), Ss0), sort(Ss0, Ss),
    findall(S-W-D, ( member(S, Ss), memberchk(S-W-D, Raw) ), Firsts).

clear_dict(S, W, D, _{sign_id:SS, truth:"false", why:WS, proof:D}) :-
    atom_string(S, SS), atom_string(W, WS).

restricting_scene_sign(S) :-
    scene_sign(S, Code),
    catalog_sign(Code, Cat, _, _),
    restricting_category(Cat).

unrelated_speed_sign(S) :-
    restricting_scene_sign(S),
    scene_sign(S, Code),
    \+ max_speed_for(Code, _),
    \+ min_speed_for(Code, _),
    \+ lane_board(Code).

unrelated_lane_sign(S) :-
    restricting_scene_sign(S),
    scene_sign(S, Code),
    \+ lane_board(Code),
    \+ lane_reserved(Code, _).

% --------------------------------------------------------------------------

permitted_clears(A, Veh, Ctx, Exclude, Cs) :-
    clears([ [S-W-clears(A, Veh, Ctx, S, W)],
             [S2-action_not_covered-unrelated_sign(A, S2)] ], Exclude, Cs).

q_permitted(A, Veh, Ctx, _{verdict:VS, reasons:R, clears:Cs}) :-
    reasons(S-T-forbids(A, Veh, Ctx, S, T), R, Ts, Signs),
    verdict_against(Ts, V), atom_string(V, VS),
    permitted_clears(A, Veh, Ctx, Signs, Cs).

q_speed(Veh, Speed, Lane, Ctx, _{verdict:VS, reasons:R, clears:Cs}) :-
    reasons(S-T-speed_violation(Veh, Speed, Lane, Ctx, S, T), R, Ts, Signs),
    verdict_against(Ts, V), atom_string(V, VS),
    clears([ [S1-W-speed_clears(Veh, Speed, Lane, Ctx, S1, W)],
             [S2-not_a_speed_sign-unrelated_speed_sign(S2)] ], Signs, Cs).

%!  q_lane(+Veh, +Lane, +Speed, +Ctx, -Out) is det.
%   May Veh use Lane (at Speed, or `none` to ignore speed)?
q_lane(Veh, Lane, Speed, Ctx, _{verdict:VS, reasons:R, clears:Cs}) :-
    reasons(S-T-lane_block(Veh, Lane, Ctx, S, T), R1, T1, S1),
    (   Speed == none
    ->  R2 = [], T2 = [], S2 = []
    ;   reasons(Sb-Tb-speed_violation(Veh, Speed, Lane, Ctx, Sb, Tb), R2, T2, S2)
    ),
    append(R1, R2, R), append(T1, T2, Ts), append(S1, S2, Signs),
    verdict_against(Ts, V), atom_string(V, VS),
    LaneT = Sc-Wc-lane_clears(Veh, Lane, Ctx, Sc, Wc),
    (   Speed == none
    ->  First = [LaneT]
    ;   First = [LaneT, Sd-Wd-speed_clears(Veh, Speed, Lane, Ctx, Sd, Wd)]
    ),
    clears([ First, [Su-not_a_lane_sign-unrelated_lane_sign(Su)] ], Signs, Cs).

%!  q_ban_times(+Action, +Veh, -Out) is det.
%   For every sign that may forbid Action for Veh: its time windows and whether
%   the ban holds inside them (true) or still depends on something else (unknown).
q_ban_times(Action, Veh, _{items:Items, clears:Cs}) :-
    findall(S, prove(forbids(Action, Veh, ctx(unknown, unknown), S, _), _), Ss0),
    sort(Ss0, Ss),
    findall(I, ( member(S, Ss), ban_item(Action, Veh, S, I) ), Items),
    permitted_clears(Action, Veh, ctx(unknown, unknown), Ss, Cs).

ban_item(Action, Veh, S, _{sign_id:SS, windows:Ws, days:DS, truth:TS, proof:D}) :-
    atom_string(S, SS),
    findall([F, To], ( plate_time(S, F, To)
                     ; group(S, G),
                       group_vehicle_truth(S, G, Veh, Tv), Tv \== false,
                       group_time(S, G, F, To) ), Ws0),
    sort(Ws0, Ws),
    sign(S, Code, _),
    ( sign_days(S, Code, Day) -> atom_string(Day, DS) ; DS = "" ),
    (   Ws = [[F0, _]|_] -> M = F0 ; M = unknown ),
    (   Day == even -> DayN = 2 ; Day == odd -> DayN = 1 ; DayN = unknown ),
    G = forbids(Action, Veh, ctx(M, DayN), S, T),
    (   prove(G, P)
    ->  atom_string(T, TS), proof_root(G, P, D)
    ;   TS = "false", D = null
    ).

%!  q_violations(+Ctx, -Out) is det.
%   items: one per observed vehicle and rule it may break.
%   clears: for each observed vehicle, the signs it does not break.
q_violations(Ctx, _{items:Items, clears:Cs}) :-
    findall(I, violation_item(Ctx, I), Items),
    findall(C, violation_clear(Ctx, C), Cs0),
    (   Cs0 == []
    ->  clears([], [], Cs)
    ;   Cs = Cs0
    ).

violation_item(Ctx, _{vehicle_id:VS, kind:"action", sign_id:SS, truth:TS, proof:D}) :-
    scene_vehicle(V, C, _, Act, _),
    action(Act),
    G = forbids(Act, veh(C, []), Ctx, S, T),
    prove(G, P),
    atom_string(V, VS), atom_string(S, SS), atom_string(T, TS),
    proof_root(G, P, D).
violation_item(Ctx, _{vehicle_id:VS, kind:"speed", sign_id:SS, truth:TS, proof:D}) :-
    scene_vehicle(V, C, Lane, _, Speed),
    number(Speed),
    G = speed_violation(veh(C, []), Speed, Lane, Ctx, S, T),
    prove(G, P),
    atom_string(V, VS), atom_string(S, SS), atom_string(T, TS),
    proof_root(G, P, D).
violation_item(Ctx, _{vehicle_id:VS, kind:"lane", sign_id:SS, truth:TS, proof:D}) :-
    scene_vehicle(V, C, Lane, _, _),
    integer(Lane),
    G = lane_block(veh(C, []), Lane, Ctx, S, T),
    prove(G, P),
    atom_string(V, VS), atom_string(S, SS), atom_string(T, TS),
    proof_root(G, P, D).
% A vehicle whose action is unknown, facing a sign that restricts some action for it.
violation_item(Ctx, _{vehicle_id:VS, kind:"unknown_action", sign_id:SS, truth:"unknown"}) :-
    scene_vehicle(V, C, _, unknown, _),
    once(( action(A), forbids(A, veh(C, []), Ctx, S, _) )),
    atom_string(V, VS), atom_string(S, SS).

violation_clear(Ctx, C) :-
    scene_vehicle(V, Cl, _, Act, _),
    action(Act),
    permitted_clears(Act, veh(Cl, []), Ctx, [], Cs),
    vehicle_clear(V, "action", Cs, C).
violation_clear(Ctx, C) :-
    scene_vehicle(V, Cl, Lane, _, Speed),
    number(Speed),
    clears([ [S1-W-speed_clears(veh(Cl, []), Speed, Lane, Ctx, S1, W)],
             [S2-not_a_speed_sign-unrelated_speed_sign(S2)] ], [], Cs),
    vehicle_clear(V, "speed", Cs, C).
violation_clear(Ctx, C) :-
    scene_vehicle(V, Cl, Lane, _, _),
    integer(Lane),
    clears([ [S-W-lane_clears(veh(Cl, []), Lane, Ctx, S, W)] ], [], Cs),
    vehicle_clear(V, "lane", Cs, C).

vehicle_clear(V, Kind, Cs, C) :-
    atom_string(V, VS),
    member(C0, Cs),
    C = C0.put(_{vehicle_id:VS, kind:Kind}).

% --------------------------------------------------------------------------
% Sign identity
% --------------------------------------------------------------------------

%!  q_is_sign(+Target, -Out) is det.  Over the selected signs: yes if every one is
%   the named sign, no if some is not.
q_is_sign(Target, _{verdict:VS, reasons:Rs}) :-
    findall(S-T-D, ( G = sign_identity(S, Target, T), prove(G, P), proof_root(G, P, D) ), Raw),
    findall(R, ( member(S1-T1-D1, Raw), reason_dict(S1, T1, D1, R) ), Rs),
    findall(T1, member(_-T1-_, Raw), Ts),
    (   Ts == [] -> V = unknown
    ;   memberchk(false, Ts) -> V = no
    ;   V = yes
    ),
    atom_string(V, VS).

% --------------------------------------------------------------------------
% Required directions (R.301 family, by placement)
% --------------------------------------------------------------------------

%!  verdict_for(+Truths, -Verdict) is det.  Truths of reasons *for* the claim.
verdict_for(Ts, yes)     :- memberchk(true, Ts), !.
verdict_for(Ts, unknown) :- memberchk(unknown, Ts), !.
verdict_for(_, no).

q_required(A, Veh, P0, Ctx, _{verdict:VS, reasons:R, clears:Cs, details:Ds}) :-
    reasons(S-T-required(A, Veh, P0, Ctx, S, T), R, Ts, Signs),
    verdict_for(Ts, V), atom_string(V, VS),
    clears([ [S1-W-requirement_clears(A, Veh, P0, Ctx, S1, W)],
             [S2-not_a_direction_sign-restricting_scene_sign(S2)] ], Signs, Cs),
    findall(D, ( scene_sign(S3, C3), direction_sign(C3), requirement_detail(S3, P0, D) ), Ds).

% --------------------------------------------------------------------------
% Time intervals with a quantifier (When.start..end, all | any)
% --------------------------------------------------------------------------

%!  q_permitted_iv(+A, +Veh, +From, +To, +Day1, +Day2, +Quant, -Out) is det.
%   Is A permitted for Veh at every (all) / some (any) moment of From..To?
%   The interval may run past midnight; minutes after midnight are on Day2.
%   Truth can only change at window edges, so the interval is checked at its ends,
%   at midnight, and at each window edge and the minutes next to it. The answer
%   carries the proof from the moment that decides it.
q_permitted_iv(A, Veh, From, To, D1, D2, Quant, Out) :-
    interval_points(From, To, D1, D2, Pts),
    findall(Ctx-O, ( member(Ctx, Pts), q_permitted(A, Veh, Ctx, O) ), Rs),
    findall(V, ( member(_-O, Rs), atom_string(V, O.verdict) ), Vs),
    quantified(Quant, Vs, Verdict),
    decisive(Quant, Verdict, Rs, ctx(M, D)-O0),
    length(Pts, N),
    atom_string(Verdict, VS),
    Out = O0.put(_{verdict:VS, minute:M, day:D, checked:N}).

quantified(all, Vs, no)      :- memberchk(no, Vs), !.
quantified(all, Vs, unknown) :- memberchk(unknown, Vs), !.
quantified(all, _, yes).
quantified(any, Vs, yes)     :- memberchk(yes, Vs), !.
quantified(any, Vs, unknown) :- memberchk(unknown, Vs), !.
quantified(any, _, no).

% the moment whose answer equals the overall verdict (the first one)
decisive(_, Verdict, Rs, R) :-
    atom_string(Verdict, VS),
    member(R, Rs), R = _-O, O.verdict == VS, !.

interval_points(From, To, D1, D2, Pts) :-
    (   From =< To
    ->  segment_points(From, To, D1, Pts)
    ;   segment_points(From, 1439, D1, P1),
        segment_points(0, To, D2, P2),
        append(P1, P2, Pts)
    ).

segment_points(A, B, D, Pts) :-
    findall(E, ( plate_time(_, F, T), member(E, [F, T]) ;
                 group_time(_, _, F, T), member(E, [F, T]) ), Edges),
    findall(M, ( member(M, [A, B])
               ; member(E, Edges), member(Dx, [-1, 0, 1]), M is E + Dx ), Ms0),
    include(between_(A, B), Ms0, Ms1),
    sort(Ms1, Ms),
    findall(ctx(M, D), member(M, Ms), Pts).

between_(A, B, M) :- M >= A, M =< B.

%!  solve_text(+Text, -Out) is det.  Entry point used by Python: Text is a goal term.
solve_text(Text, Out) :-
    term_string(Goal, Text),
    Goal =.. [Name|Args],
    append(Args, [Out], Args1),
    G1 =.. [Name|Args1],
    call(G1).
