"use strict";

// The supplied 3.6 WebGL renderer skips clipEndWithSlot for null/non-renderable
// attachments. Draw ranges terminate clipping even when its end slot is hidden.
// Use public range arguments; do not mutate the skeleton or the external runtime.
function drawWithClipBoundaries(renderer, batcher, skeleton, spineRuntime) {
    const order = skeleton.drawOrder;
    let start = 0;
    let active = null;
    for (let i = 0; i < order.length; i++) {
        const slot = order[i];
        const attachment = slot.getAttachment();
        if (active === null && attachment instanceof spineRuntime.ClippingAttachment) {
            active = attachment;
        }
        if (active !== null && active.endSlot === slot.data) {
            renderer.draw(batcher, skeleton, order[start].data.index, slot.data.index);
            start = i + 1;
            active = null;
        }
    }
    if (start < order.length) {
        renderer.draw(batcher, skeleton, order[start].data.index, order[order.length - 1].data.index);
    }
}
