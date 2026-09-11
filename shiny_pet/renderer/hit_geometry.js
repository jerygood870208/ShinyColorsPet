"use strict";
function captureHitGeometry(skeleton, spineRuntime, projection) {
    const point = (x,y) => [(x-projection.x)/projection.width,
        1-(y-projection.y)/projection.height];
    const bounds = new spineRuntime.SkeletonBounds();
    bounds.update(skeleton, false);
    const attachments = bounds.polygons.map((vertices,i) => {
        const points=[];
        for(let j=0;j<vertices.length;j+=2) points.push(point(vertices[j],vertices[j+1]));
        return {name:bounds.boundingBoxes[i].name,points};
    });
    const offset=new spineRuntime.Vector2(), size=new spineRuntime.Vector2();
    skeleton.getBounds(offset,size,[]);
    const model = size.x>0 && size.y>0 ? [point(offset.x,offset.y),
        point(offset.x+size.x,offset.y),point(offset.x+size.x,offset.y+size.y),
        point(offset.x,offset.y+size.y)] : null;
    return {attachments,model};
}
