/*  Meta-interpreter that returns a proof tree (DESIGN.md, "Knowledge base and rule engine").

    prove(+Goal, -Proof) runs Goal like call/1 but builds a proof:

      rule(Goal, BodyProof)     a rule clause fired
      fact(Goal, Source)        a catalog or scene fact; Source = src(Law, Article) | scene | none
      cite(RuleId, Law, Art)    a cite/1 marker inside a rule body
      leaf(Goal)                a helper evaluated directly (declared with leaf/1)
      naf(Goal)                 \+ Goal succeeded (Goal had no proof)
      builtin(Goal)             a built-in or library predicate
      and(P1, P2)               conjunction

    Rule bodies may use ',', ';', '->', '\+' and cite/1, but no cuts: the
    interpreter does not implement cut, so rules use if-then-else or
    mutually exclusive clauses instead.
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

%!  cite(+RuleId) is det.  No-op marker; the meta-interpreter turns it into a citation.
cite(_).

prove(true, true) :- !.
prove((A, B), and(PA, PB)) :- !,
    prove(A, PA),
    prove(B, PB).
prove((C -> T ; E), P) :- !,
    (   prove(C, PC)
    ->  prove(T, PT), P = and(PC, PT)
    ;   prove(E, P)
    ).
prove((C -> T), and(PC, PT)) :- !,
    prove(C, PC) -> prove(T, PT).
prove((A ; B), P) :- !,
    (   prove(A, P)
    ;   prove(B, P)
    ).
prove(\+ G, naf(G)) :- !,
    \+ prove(G, _).
prove(cite(R), cite(R, L, A)) :- !,
    (   rule_source(R, L, A)
    ->  true
    ;   L = none, A = none
    ).
prove(G, leaf(G)) :-
    leaf(G), !,
    once(G).
prove(G, fact(G, Src)) :-
    fact_pred(G), !,
    call(G),
    fact_source(G, Src).
prove(G, builtin(G)) :-
    predicate_property(G, built_in), !,
    call(G).
prove(G, builtin(G)) :-
    predicate_property(G, imported_from(_)), !,
    call(G).
prove(G, rule(G, P)) :-
    clause(G, Body),
    prove(Body, P).

% --------------------------------------------------------------------------
% Proof tree -> dicts (janus converts SWI dicts to Python dicts)
% --------------------------------------------------------------------------

%!  proof_dicts(+Proof, -Nodes:list) is det.
proof_dicts(true, []) :- !.
proof_dicts(and(A, B), Ns) :- !,
    proof_dicts(A, NA),
    proof_dicts(B, NB),
    append(NA, NB, Ns).
proof_dicts(builtin(_), []) :- !.
proof_dicts(rule(G, P), [_{type:"rule", goal:S, children:Cs}]) :- !,
    goal_string(G, S),
    proof_dicts(P, Cs).
proof_dicts(fact(G, Src), [D]) :- !,
    goal_string(G, S),
    (   Src = src(L, A)
    ->  atom_string(L, LS), atom_string(A, AS),
        D = _{type:"fact", goal:S, source:_{law_id:LS, article_id:AS}}
    ;   D = _{type:"fact", goal:S}
    ).
proof_dicts(cite(R, L, A), [D]) :- !,
    atom_string(R, RS),
    (   L == none
    ->  D = _{type:"cite", rule:RS}
    ;   atom_string(L, LS), atom_string(A, AS),
        D = _{type:"cite", rule:RS, source:_{law_id:LS, article_id:AS}}
    ).
proof_dicts(leaf(G), [_{type:"leaf", goal:S}]) :- !,
    goal_string(G, S).
proof_dicts(naf(G), [_{type:"naf", goal:S}]) :- !,
    goal_string(G, S).

%!  proof_root(+Goal, +Proof, -Dict) is det.  One root node for a top-level goal.
proof_root(G, P, _{type:"rule", goal:S, children:Cs}) :-
    goal_string(G, S),
    proof_dicts(P, Cs0),
    (   Cs0 = [_{type:"rule", goal:S, children:Inner}]
    ->  Cs = Inner
    ;   Cs = Cs0
    ).

goal_string(G, S) :-
    copy_term(G, G1),
    numbervars(G1, 0, _),
    format(string(S), "~W", [G1, [quoted(true), numbervars(true)]]).
