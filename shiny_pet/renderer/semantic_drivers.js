/* Manifest-defined drivers. No character-specific bone, slot or animation names. */
"use strict";
function createSemanticDrivers(skeleton, state) {
    let mouth={driver:"disabled"}, gaze={driver:"disabled"}, channels={};
    let mouthValue=[0,0], gazeValue=[0,0], expressionSlots={};
    const controlled=[];
    function animate(config,name,alpha=1) {
        const track=channels[config.channel];
        let entry=state.getCurrent(track);
        if(!entry || entry.animation.name!==name) {
            entry=state.setAnimation(track,name,true);
            entry.mixDuration=.1;
        }
        entry.alpha=alpha;
    }
    function restoreBones() {
        for(const [bone,x,y,rotation] of [...controlled].reverse()) {
            bone.x=x;bone.y=y;bone.rotation=rotation;
        }
        controlled.length=0;
    }
    function bone(config,x,y) {
        const b=skeleton.findBone(config.bone);
        if(!b)return;
        controlled.push([b,b.x,b.y,b.rotation]);
        b.x+=x*(config.x_range||0);
        b.y+=y*(config.y_range||0);
        b.rotation+=x*(config.rotation_range||0);
    }
    return {
        configure(m,g,c){mouth=m;gaze=g;channels=c;},
        mouth(open,form,emotion="neutral"){
            mouthValue=[open,form];
            if(mouth.driver==="bone" || mouth.driver==="disabled")return;
            const track=channels[mouth.channel];
            if(open===0){
                if(mouth.candidates.includes("lip_wait_s")){
                    animate(mouth,"lip_wait_s",1);
                    return;
                }
                if(state.getCurrent(track)){
                    restoreBones();
                    state.clearTrack(track);
                }
                return;
            }
            const names=mouth.candidates;
            const selection=mouth.driver==="animation_choice"?open:(form+1)/2;
            // *_s are closed poses, not speaking animations. Only use available names.
            const families={happy:"smile",smile:"smile",greeting:"smile",excited:"smile",
                smug:"smile",mischievous:"smile",sad:"sad",crying:"sad",troubled:"sad",
                angry:"anger",angry_strong:"anger",surprised:"surp",afraid:"surp",
                panicked:"surp",shy:"shy",neutral:"wait",serious:"wait",cool:"wait",
                sleepy:"wait",thinking:"wait",agree:"wait",disagree:"wait"};
            const family=families[emotion] || "wait";
            const preferred=mouth.driver==="animation_mix"
                ?["lip_"+family,...names.filter(n=>n.startsWith("lip_"+family)&&!n.endsWith("_s")),
                  "lip_wait","lip_a"].map(n=>names.indexOf(n)).find(i=>i>=0) ?? -1:-1;
            const index=preferred>=0?preferred:Math.min(names.length-1,Math.floor(selection*names.length));
            animate(mouth,names[index],mouth.driver==="animation_mix"?open:1);
        },
        gaze(x,y){
            gazeValue=[x,y];
            if(gaze.driver==="animation_choice")animate(gaze,x<-.25?gaze.left:x>.25?gaze.right:gaze.center);
        },
        expression(slot,attachment){expressionSlots={[slot]:attachment};},
        clearExpressions(){
            for(const slot of Object.keys(expressionSlots))skeleton.findSlot(slot).setToSetupPose();
            expressionSlots={};
        },
        beforeApply:restoreBones,
        afterApply(){
            if(mouth.driver==="bone")bone(mouth,mouthValue[0],mouthValue[1]);
            if(gaze.driver==="bone")bone(gaze,gazeValue[0],gazeValue[1]);
            for(const [slot,attachment] of Object.entries(expressionSlots))skeleton.setAttachment(slot,attachment);
        },
        reset(){restoreBones();mouthValue=[0,0];gazeValue=[0,0];expressionSlots={};}
    };
}
if(typeof module!=="undefined")module.exports={createSemanticDrivers};
