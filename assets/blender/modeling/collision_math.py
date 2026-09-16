"""Distance checks on primitive proxies; independent of Blender and its solver."""
import math


def dot(a,b): return sum(x*y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def add(a,b): return tuple(x+y for x,y in zip(a,b))
def mul(a,k): return tuple(x*k for x in a)
def length(a): return math.sqrt(dot(a,a))


def segment_box_distance(a,b,half):
    """Exact segment/AABB distance by minimizing each piecewise quadratic interval."""
    d=sub(b,a); cuts={0.,1.}
    for i in range(3):
        if abs(d[i])>1e-12:
            for edge in (-half[i],half[i]):
                t=(edge-a[i])/d[i]
                if 0<t<1: cuts.add(t)
    def distance(t):
        return sum(max(abs(a[i]+t*d[i])-half[i],0.)**2 for i in range(3))
    ordered=sorted(cuts); best=min(distance(t) for t in ordered)
    for lo,hi in zip(ordered,ordered[1:]):
        mid=(lo+hi)/2; aa=bb=0.
        for i in range(3):
            p=a[i]+mid*d[i]
            if abs(p)>half[i]:
                v=a[i]-math.copysign(half[i],p);aa+=d[i]**2;bb+=d[i]*v
        if aa>1e-12: best=min(best,distance(max(lo,min(hi,-bb/aa))))
    return math.sqrt(max(best,0.))


def segment_segment_distance(p1,q1,p2,q2):
    d1=sub(q1,p1);d2=sub(q2,p2);r=sub(p1,p2)
    a=dot(d1,d1);e=dot(d2,d2);f=dot(d2,r)
    clamp=lambda x:max(0.,min(1.,x))
    if a<=1e-12 and e<=1e-12:return length(r)
    if a<=1e-12:s=0.;t=clamp(f/e)
    else:
        c=dot(d1,r)
        if e<=1e-12:t=0.;s=clamp(-c/a)
        else:
            b=dot(d1,d2);denom=a*e-b*b
            s=clamp((b*f-c*e)/denom) if abs(denom)>1e-12 else 0.
            t=(b*s+f)/e
            if t<0:t=0.;s=clamp(-c/a)
            elif t>1:t=1.;s=clamp((b-c)/a)
    return length(sub(add(p1,mul(d1,s)),add(p2,mul(d2,t))))
