/*  Fact predicates: the sign catalog (asserted once from kb/sign_catalog.yaml by
    vqa.kb.Catalog.facts) and the current scene (asserted per query by
    vqa.reasoning.facts.scene_facts). All are dynamic so Python can load them.
*/

% ---- catalog facts (one set per process)
:- dynamic catalog_sign/4,       % catalog_sign(Code, Category, LawId, ArticleId)
           prohibits/3,          % prohibits(Code, Action, [spec(Class, Conds), ...])
           catalog_except/2,     % catalog_except(Code, Class)
           no_priority_exempt/1, % no_priority_exempt(Code)
           value_cond/4,         % value_cond(Code, Class, Attr, Op)
           catalog_days/2,       % catalog_days(Code, even|odd)
           max_speed_for/2,      % max_speed_for(Code, Class)
           min_speed_for/2,      % min_speed_for(Code, Class)
           lane_board/1,         % lane_board(Code)
           lane_reserved/2,      % lane_reserved(Code, Class)
           direction_sign/1,     % direction_sign(Code)
           only_direction/2,     % only_direction(Code, Action)
           ends/2.               % ends(EndCode, EndedCode)

% ---- scene facts (replaced for every query)
:- dynamic sign/3,               % sign(S, Code, Confidence)
           sign_value/2,         % sign_value(S, Number)
           sign_lane/3,          % sign_lane(S, Lane, plate|position)  S.504 plate or position.lane
           plate_time/3,         % plate_time(S, FromMin, ToMin)   S.508, minutes after midnight
           plate_days/2,         % plate_days(S, even|odd)     S.508
           plate_vehicle/2,      % plate_vehicle(S, Spec)      S.505a
           plate_except/2,       % plate_except(S, Spec)       S.H,6
           lane_limit/4,         % lane_limit(S, Lane, Spec|any, MaxKmh)
           lane_min/4,           % lane_min(S, Lane, Spec|any, MinKmh)
           lane_vehicle/3,       % lane_vehicle(S, Lane, Spec)  lane open only to these
           scene_vehicle/5,      % scene_vehicle(V, Class, Lane|unknown, Action, Speed|unknown)
           selected/1,           % selected(S): restrict reasoning to these signs
           selection_active/0.

scene_fact(sign/3).        scene_fact(sign_value/2).   scene_fact(sign_lane/3).
scene_fact(plate_time/3).  scene_fact(plate_days/2).   scene_fact(plate_vehicle/2).
scene_fact(plate_except/2). scene_fact(lane_limit/4).  scene_fact(lane_min/4).
scene_fact(lane_vehicle/3). scene_fact(scene_vehicle/5).
scene_fact(selected/1).    scene_fact(selection_active/0).

catalog_fact(catalog_sign/4). catalog_fact(prohibits/3). catalog_fact(catalog_except/2).
catalog_fact(no_priority_exempt/1). catalog_fact(value_cond/4). catalog_fact(catalog_days/2).
catalog_fact(max_speed_for/2). catalog_fact(min_speed_for/2). catalog_fact(lane_board/1).
catalog_fact(lane_reserved/2). catalog_fact(direction_sign/1). catalog_fact(only_direction/2).
catalog_fact(ends/2).

clear_scene :-
    forall(scene_fact(N/A), (functor(H, N, A), retractall(H))).

clear_catalog :-
    forall(catalog_fact(N/A), (functor(H, N, A), retractall(H))).

%!  add_facts(+Text:string) is det.  Assert a Prolog list of facts written by Python.
add_facts(Text) :-
    term_string(Facts, Text),
    must_be(list, Facts),
    forall(member(F, Facts), assertz(F)).

% ---- for the meta-interpreter
fact_pred(G) :-
    functor(G, N, A),
    (   scene_fact(N/A) ; catalog_fact(N/A) ; ontology_fact(N/A) ), !.

ontology_fact(is_a/2).

%!  fact_source(+Fact, -Source) is det.  Catalog facts cite the sign's article.
fact_source(G, src(L, A)) :-
    functor(G, N, Ar), catalog_fact(N/Ar),
    arg(1, G, Code), atom(Code),
    catalog_sign(Code, _, L, A), !.
fact_source(G, scene) :-
    functor(G, N, A), scene_fact(N/A), !.
fact_source(_, none).

%!  scene_sign(?S, ?Code) is nondet.  Signs in the scene, honouring a selection.
scene_sign(S, Code) :-
    sign(S, Code, _),
    (   selection_active
    ->  selected(S)
    ;   true
    ).
