/*  Top-level queries called from Python (vqa/reasoning/engine.py).

    Each solve_* collects every reason (sign + truth + proof) and combines the
    truths into a verdict: any true reason decides, otherwise any unknown
    reason makes the verdict unknown. The combination is closed-world over
    the signs in the scene: no reason means no visible sign restricts it.
*/

%!  reasons(:Template, -Reasons:list(dict), -Truths:list) is det.
%   Template = S-T-Goal. Keeps the strongest reason per sign (true over unknown).
reasons(S-T-Goal, Reasons, Truths) :-
    findall(S-T-D, ( prove(Goal, P), proof_root(Goal, P, D) ), Raw),
    best_per_sign(Raw, Best),
    findall(R, ( member(S1-T1-D1, Best), reason_dict(S1, T1, D1, R) ), Reasons),
    findall(T1, member(_-T1-_, Best), Truths).

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

% --------------------------------------------------------------------------

%!  solve_permitted(+Action, +Veh, +Ctx, -Verdict, -Reasons) is det.
solve_permitted(Action, Veh, Ctx, Verdict, Reasons) :-
    reasons(S-T-forbids(Action, Veh, Ctx, S, T), Reasons, Ts),
    verdict_against(Ts, Verdict).

%!  solve_speed(+Veh, +Speed, +Lane, +Ctx, -Verdict, -Reasons) is det.
solve_speed(Veh, Speed, Lane, Ctx, Verdict, Reasons) :-
    reasons(S-T-speed_violation(Veh, Speed, Lane, Ctx, S, T), Reasons, Ts),
    verdict_against(Ts, Verdict).

%!  solve_lane(+Veh, +Lane, +Speed, +Ctx, -Verdict, -Reasons) is det.
%   May Veh use Lane (at Speed, or `none` to ignore speed)?
solve_lane(Veh, Lane, Speed, Ctx, Verdict, Reasons) :-
    reasons(S-T-lane_block(Veh, Lane, Ctx, S, T), R1, T1),
    (   Speed == none
    ->  R2 = [], T2 = []
    ;   reasons(S2-T3-speed_violation(Veh, Speed, Lane, Ctx, S2, T3), R2, T2)
    ),
    append(R1, R2, Reasons),
    append(T1, T2, Ts),
    verdict_against(Ts, Verdict).

%!  solve_ban_times(+Action, +Veh, -Items) is det.
%   For every sign that may forbid Action for Veh: its time windows and whether
%   the ban holds inside them (true) or still depends on something else (unknown).
solve_ban_times(Action, Veh, Items) :-
    findall(S, prove(forbids(Action, Veh, ctx(unknown, unknown), S, _), _), Ss0),
    sort(Ss0, Ss),
    findall(I, ( member(S, Ss), ban_item(Action, Veh, S, I) ), Items).

ban_item(Action, Veh, S, _{sign_id:SS, windows:Ws, days:DS, truth:TS, proof:D}) :-
    atom_string(S, SS),
    findall([F, To], plate_time(S, F, To), Ws),
    sign(S, Code, _),
    ( sign_days(S, Code, Day) -> atom_string(Day, DS) ; DS = "" ),
    (   Ws = [[F0, _]|_] -> M = F0 ; M = unknown ),
    (   Day == even -> DayN = 2 ; Day == odd -> DayN = 1 ; DayN = unknown ),
    G = forbids(Action, Veh, ctx(M, DayN), S, T),
    (   prove(G, P)
    ->  atom_string(T, TS), proof_root(G, P, D)
    ;   TS = "false", D = null
    ).

%!  solve_violations(+Ctx, -Items) is det.
%   One item per observed vehicle and rule it may break.
solve_violations(Ctx, Items) :-
    findall(I, violation_item(Ctx, I), Items).

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

%!  solve_text(+Text, -Out) is det.  Entry point used by Python: Text is a goal term.
solve_text(Text, Out) :-
    term_string(Goal, Text),
    Goal =.. [Name|Args],
    append(Args, [Out], Args1),
    G1 =.. [Name|Args1],
    call(G1).

% Wrappers with a single output dict, so Python reads one binding.
q_permitted(A, Veh, Ctx, _{verdict:VS, reasons:R}) :-
    solve_permitted(A, Veh, Ctx, V, R), atom_string(V, VS).
q_speed(Veh, Speed, Lane, Ctx, _{verdict:VS, reasons:R}) :-
    solve_speed(Veh, Speed, Lane, Ctx, V, R), atom_string(V, VS).
q_lane(Veh, Lane, Speed, Ctx, _{verdict:VS, reasons:R}) :-
    solve_lane(Veh, Lane, Speed, Ctx, V, R), atom_string(V, VS).
q_ban_times(A, Veh, _{items:I}) :-
    solve_ban_times(A, Veh, I).
q_violations(Ctx, _{items:I}) :-
    solve_violations(Ctx, I).
