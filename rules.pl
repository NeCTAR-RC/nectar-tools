% -*- mode: prolog -*-

sum_list([], 0).
sum_list([H | Rest], Sum) :- sum_list(Rest,Tmp), Sum is H + Tmp.

add_category_min_score(In, Category, Min,  P) :-
  gerrit:commit_author(A),
  findall(X, gerrit:commit_label(label(Category,X),R),Y),
  findall(X, gerrit:commit_label(label(Category,X),A),Z),
  sum_list(Y, Total_sum),
  sum_list(Z, Author_sum),
  Sum is Total_sum - Author_sum,
  Sum >= Min, !,
  P = [label(Category, ok(R)) | In].

add_category_min_score(In, Category,Min,P) :-
  P = [label(Category,need(Min)) | In].

submit_rule(S) :-
  gerrit:default_submit(X),
  X =.. [submit | Ls],
  gerrit:remove_label(Ls,label('Code-Review',_),NoCR),
  add_category_min_score(NoCR,'Code-Review', 2, Labels),
  S =.. [submit | Labels].
