from bounded_merges import weight,make,serialize,parse,measure,nx
def test_exact_objective():
    # A accessed twice, B once; shared by one request.
    assert weight((10,5,3),(20,7,2),(30,9),2,100,25)==-(200*(9-5-7-24)+100*(18-10-7)+25*(60-20-20))
def test_bounds_and_roundtrip():
    files={"A":b"alpha beta gamma "*100,"B":b"alpha beta gamma "*100,"C":b"tiny"}
    g=nx.DiGraph();g.add_nodes_from(files);g.add_edge("A","B")
    closures={"A":{"A","B"},"B":{"B"},"C":{"C"}}
    groups,frames,_,full=make(files,g,{"A":1,"B":3,"C":0},2,"matching",100,25)
    payload,directory=serialize(files,groups,frames);mapping,meta=parse(directory,payload)
    for n,(i,_,size,_) in mapping.items():
        _,z,raw=meta[i];assert 2*raw<=5*size and 2*z<=3*full[n]
    assert measure(files,payload,mapping,meta,closures,["A","C"])["checks"]==3
