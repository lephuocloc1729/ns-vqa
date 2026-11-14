/*  Rule family: sign identity ("Đây là biển X, đúng hay sai?").

    sign_identity(+S, +Target, -T): scene sign S is (T = true) or is not (false)
    the sign named by Target:
      codes(Atoms)   one of these catalog codes (a family code is expanded in Python)
      meaning(M)     a catalog key or tag
      category(C)    a sign group: prohibitory, mandatory, warning, information, ...
    The catalog fact for the sign's own code is in the proof, so the answer cites
    that sign's article; category claims also cite art. 11 (sign groups).
*/

:- multifile leaf/1.
:- discontiguous leaf/1.

sign_identity(S, codes(As), T) :-
    scene_sign(S, Code),
    catalog_sign(Code, _, _, _),
    code_truth(Code, As, T).
sign_identity(S, meaning(M), T) :-
    scene_sign(S, Code),
    catalog_sign(Code, _, _, _),
    meaning_truth(Code, M, T).
sign_identity(S, category(C), T) :-
    scene_sign(S, Code),
    catalog_sign(Code, Cat, _, _),
    cite(r_sign_groups),
    ( Cat == C -> T = true ; T = false ).

leaf(code_truth(_, _, _)).
code_truth(Code, As, T) :- ( memberchk(Code, As) -> T = true ; T = false ).

leaf(meaning_truth(_, _, _)).
meaning_truth(Code, M, T) :-
    ( ( catalog_key(Code, M) ; catalog_tag(Code, M) ) -> T = true ; T = false ).
