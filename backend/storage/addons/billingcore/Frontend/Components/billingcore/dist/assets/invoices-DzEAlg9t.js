import{$ as e,$t as t,Ar as n,C as r,Dr as i,E as a,Et as o,Kn as s,N as c,Nr as l,Ot as u,Q as d,Rt as f,Tt as p,Vn as m,Zt as h,_r as g,_t as _,at as v,bn as y,c as b,d as x,dn as S,en as C,gt as w,ht as T,i as E,jr as D,l as O,lr as k,n as A,o as j,p as M,pn as N,s as P,sn as F,t as I,u as L,v as R,vt as z,wr as B,x as V,yn as H,yt as U}from"./dist-cXZpAOgx.js";import{a as ee,c as W,d as te,f as G,h as K,i as ne,l as q,m as J,n as re,o as ie,r as ae,s as oe,t as se,u as Y}from"./eye-CSpDDQIh.js";import{C as ce,S as le,T as ue,_ as de,a as fe,b as pe,c as me,d as he,f as ge,g as _e,h as ve,i as ye,l as be,m as xe,n as Se,o as Ce,p as we,r as X,s as Te,t as Ee,u as De,v as Z,w as Oe,x as ke,y as Ae}from"./SelectValue-jmjolKcH.js";import{t as je}from"./RovingFocusGroup-DH8GkbYx.js";import{n as Me,t as Ne}from"./file-text-Pw7CZ4TR.js";import{t as Pe}from"./usePanelTimezone-HYvxZ6yG.js";var Fe=[`INPUT`,`TEXTAREA`];function Ie(e,t,n,r={}){if(!t||r.enableIgnoredElement&&Fe.includes(t.nodeName))return null;let{arrowKeyOptions:i=`both`,attributeName:a=`[data-reka-collection-item]`,itemsArray:o=[],loop:s=!0,dir:c=`ltr`,preventScroll:l=!0,focus:u=!1}=r,[d,f,p,m,h,g]=[e.key===`ArrowRight`,e.key===`ArrowLeft`,e.key===`ArrowUp`,e.key===`ArrowDown`,e.key===`Home`,e.key===`End`],_=p||m,v=d||f;if(!h&&!g&&(!_&&!v||i===`vertical`&&v||i===`horizontal`&&_))return null;let y=n?Array.from(n.querySelectorAll(a)):o;if(!y.length)return null;l&&e.preventDefault();let b=null;return v||_?b=Le(y,t,{goForward:_?m:c===`ltr`?d:f,loop:s}):h?b=y.at(0)||null:g&&(b=y.at(-1)||null),u&&b?.focus(),b}function Le(e,t,n,r=e.includes(t)?e.length:e.length+1){if(--r===0)return null;let i=e.indexOf(t),a;if(a=i===-1?n.goForward?0:e.length-1:n.goForward?i+1:i-1,!n.loop&&(a<0||a>=e.length))return null;let o=e[(a+e.length)%e.length];return o?o.hasAttribute(`disabled`)&&o.getAttribute(`disabled`)!==`false`?Le(e,o,n,r):o:null}var Re=u({__name:`MenuAnchor`,props:{reference:{type:null,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1}},setup(e){let t=e;return(e,n)=>(N(),_(i(be),D(f(t)),{default:s(()=>[y(e.$slots,`default`)]),_:3},16))}});function ze(){let e=g(!1);return F(()=>{R(`keydown`,()=>{e.value=!0},{capture:!0,passive:!0}),R([`pointerdown`,`pointermove`],()=>{e.value=!1},{capture:!0,passive:!0})}),e}var Be=r(ze),[Q,Ve]=K([`MenuRoot`,`MenuSub`],`MenuContext`),[$,He]=K(`MenuRoot`),Ue=u({__name:`MenuRoot`,props:{open:{type:Boolean,required:!1,default:!1},dir:{type:String,required:!1},modal:{type:Boolean,required:!1,default:!0}},emits:[`update:open`],setup(e,{emit:t}){let n=e,r=t,{modal:a,dir:o}=B(n),c=G(o),l=V(n,`open`,r),u=g(),d=Be();return Ve({open:l,onOpenChange:e=>{l.value=e},content:u,onContentChange:e=>{u.value=e}}),He({onClose:()=>{l.value=!1},isUsingKeyboardRef:d,dir:c,modal:a}),(e,t)=>(N(),_(i(De),null,{default:s(()=>[y(e.$slots,`default`)]),_:3}))}}),[We,Ge]=K(`MenuContent`),Ke=u({__name:`MenuContentImpl`,props:h({loop:{type:Boolean,required:!1},disableOutsidePointerEvents:{type:Boolean,required:!1},disableOutsideScroll:{type:Boolean,required:!1},trapFocus:{type:Boolean,required:!1},memoDependencies:{type:Array,required:!1},side:{type:null,required:!1},sideOffset:{type:Number,required:!1},sideFlip:{type:Boolean,required:!1},align:{type:null,required:!1},alignOffset:{type:Number,required:!1},alignFlip:{type:Boolean,required:!1},avoidCollisions:{type:Boolean,required:!1},collisionBoundary:{type:null,required:!1},collisionPadding:{type:[Number,Object],required:!1},arrowPadding:{type:Number,required:!1},hideShiftedArrow:{type:Boolean,required:!1},sticky:{type:String,required:!1},hideWhenDetached:{type:Boolean,required:!1},positionStrategy:{type:String,required:!1},updatePositionStrategy:{type:String,required:!1},disableUpdateOnLayoutShift:{type:Boolean,required:!1},prioritizePosition:{type:Boolean,required:!1},reference:{type:null,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1}},{...Te}),emits:[`escapeKeyDown`,`pointerDownOutside`,`focusOutside`,`interactOutside`,`entryFocus`,`openAutoFocus`,`closeAutoFocus`,`dismiss`],setup(e,{emit:t}){let n=e,r=t,a=Q(),c=$(),{trapFocus:l,disableOutsidePointerEvents:u,loop:d}=B(n);Oe(),ue(u.value);let f=g(``),p=g(0),h=g(0),v=g(null),b=g(`right`),x=g(0),C=g(null),w=g(),{forwardRef:T,currentElement:E}=M(),{handleTypeaheadSearch:D}=le(),O=g();function k(e){let t=Ie(e,O.value||J(),E.value,{loop:d.value,arrowKeyOptions:`vertical`,dir:c?.dir.value,focus:!1,attributeName:`[data-reka-collection-item]:not([data-disabled])`});t&&(O.value=t,t.scrollIntoView({block:`nearest`}))}function A(){O.value&&O.value.click()}let j=g(),P=g();m(O,e=>{if(P.value&&(e===void 0||e!==P.value.trigger.value)){if(e===void 0)return;P.value.onOpenChange(!1),P.value=void 0}}),m(E,e=>{a.onContentChange(e)}),S(()=>{window.clearTimeout(p.value)});function F(e){return b.value===v.value?.side&&Ae(e,v.value?.area)}async function I(e){r(`openAutoFocus`,e),!e.defaultPrevented&&(e.preventDefault(),E.value?.focus({preventScroll:!0}))}function L(e){if(e.defaultPrevented)return;let t=e.target,n=t.closest(`[data-reka-menu-content]`)===e.currentTarget,r=[`input`,`textarea`].includes(t.tagName.toLowerCase()),i=e.ctrlKey||e.altKey||e.metaKey,a=e.key.length===1,o=Ie(e,J(),E.value,{loop:d.value,arrowKeyOptions:`vertical`,dir:c?.dir.value,focus:!0,attributeName:`[data-reka-collection-item]:not([data-disabled])`});if(o)return o?.focus();if(e.code===`Space`)return;let s=w.value?.getItems()??[];if(n&&(e.key===`Tab`&&c.modal.value&&e.preventDefault(),!i&&a&&!r&&D(e.key,s)),e.target!==E.value||!ge.includes(e.key))return;e.preventDefault();let l=[...s.map(e=>e.ref)];xe.includes(e.key)&&l.reverse(),_e(l)}function R(e){e?.currentTarget?.contains?.(e.target)||(window.clearTimeout(p.value),f.value=``)}function z(e){if(!Z(e))return;let t=e.target,n=x.value!==e.clientX;if((e?.currentTarget)?.contains(t)&&n){let t=e.clientX>x.value?`right`:`left`;b.value=t,x.value=e.clientX}}function V(e){Z(e)&&j.value&&j.value.focus()}return Ge({onItemEnter:e=>!!F(e),onItemLeave:e=>F(e)?!0:([`INPUT`,`TEXTAREA`].includes(J()?.tagName||``)||E.value?.focus(),C.value=null,!1),onTriggerLeave:e=>!!F(e),searchRef:f,highlightedElement:O,onKeydownNavigation:k,onKeydownEnter:A,filterElement:j,onFilterElementChange:e=>{j.value=e},activeSubmenuContext:P,pointerGraceTimerRef:h,onPointerGraceIntentChange:e=>{v.value=e}}),(e,t)=>(N(),_(i(pe),{"as-child":``,trapped:i(l),onMountAutoFocus:I,onUnmountAutoFocus:t[7]||=e=>r(`closeAutoFocus`,e)},{default:s(()=>[o(i(ke),{"as-child":``,"disable-outside-pointer-events":i(u),onEscapeKeyDown:t[2]||=e=>r(`escapeKeyDown`,e),onPointerDownOutside:t[3]||=e=>r(`pointerDownOutside`,e),onFocusOutside:t[4]||=e=>r(`focusOutside`,e),onInteractOutside:t[5]||=e=>r(`interactOutside`,e),onDismiss:t[6]||=e=>r(`dismiss`)},{default:s(()=>[o(i(je),{ref_key:`rovingFocusGroupRef`,ref:w,"current-tab-stop-id":C.value,"onUpdate:currentTabStopId":t[0]||=e=>C.value=e,"as-child":``,orientation:`vertical`,dir:i(c).dir.value,loop:i(d),onEntryFocus:t[1]||=e=>{r(`entryFocus`,e),i(c).isUsingKeyboardRef.value||e.preventDefault()}},{default:s(()=>[o(i(me),{ref:i(T),role:`menu`,as:e.as,"as-child":e.asChild,"aria-orientation":`vertical`,"data-reka-menu-content":``,"data-state":i(de)(i(a).open.value),dir:i(c).dir.value,side:e.side,"side-offset":e.sideOffset,align:e.align,"align-offset":e.alignOffset,"avoid-collisions":e.avoidCollisions,"collision-boundary":e.collisionBoundary,"collision-padding":e.collisionPadding,"arrow-padding":e.arrowPadding,"prioritize-position":e.prioritizePosition,"position-strategy":e.positionStrategy,"update-position-strategy":e.updatePositionStrategy,sticky:e.sticky,"hide-when-detached":e.hideWhenDetached,reference:e.reference,onKeydown:L,onBlur:R,onPointermove:z,onPointerenter:V},{default:s(()=>[y(e.$slots,`default`)]),_:3},8,[`as`,`as-child`,`data-state`,`dir`,`side`,`side-offset`,`align`,`align-offset`,`avoid-collisions`,`collision-boundary`,`collision-padding`,`arrow-padding`,`prioritize-position`,`position-strategy`,`update-position-strategy`,`sticky`,`hide-when-detached`,`reference`])]),_:3},8,[`current-tab-stop-id`,`dir`,`loop`])]),_:3},8,[`disable-outside-pointer-events`])]),_:3},8,[`trapped`]))}}),qe=u({inheritAttrs:!1,__name:`MenuItemImpl`,props:{disabled:{type:Boolean,required:!1},textValue:{type:String,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1}},setup(e){let n=e,r=We(),{forwardRef:a,currentElement:c}=M(),{CollectionItem:l}=ie(),u=g(!1),d=T(()=>u.value||c.value!=null&&r.highlightedElement.value===c.value);async function f(e){if(!(e.defaultPrevented||!Z(e))){if(n.disabled)r.onItemLeave(e);else if(!r.onItemEnter(e)){let t=e.currentTarget;r.highlightedElement.value=t,[`INPUT`,`TEXTAREA`].includes(J()?.tagName||``)||t.focus({preventScroll:!0})}}}async function p(e){await C(),!e.defaultPrevented&&Z(e)&&r.highlightedElement.value===c.value&&!r.onItemLeave(e)&&r.highlightedElement.value===c.value&&(r.highlightedElement.value=void 0)}return(e,n)=>(N(),_(i(l),{value:{textValue:e.textValue}},{default:s(()=>[o(i(x),t({ref:i(a),role:`menuitem`,tabindex:`-1`},e.$attrs,{as:e.as,"as-child":e.asChild,"aria-disabled":e.disabled||void 0,"data-disabled":e.disabled?``:void 0,"data-highlighted":d.value?``:void 0,onPointermove:f,onPointerleave:p,onFocus:n[0]||=async t=>{await C(),!(t.defaultPrevented||e.disabled)&&(u.value=!0,i(r).highlightedElement.value=t.currentTarget)},onBlur:n[1]||=async e=>{await C(),!e.defaultPrevented&&(u.value=!1)}}),{default:s(()=>[y(e.$slots,`default`)]),_:3},16,[`as`,`as-child`,`aria-disabled`,`data-disabled`,`data-highlighted`])]),_:3},8,[`value`]))}}),Je=u({__name:`MenuItem`,props:{disabled:{type:Boolean,required:!1},textValue:{type:String,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1}},emits:[`select`],setup(e,{emit:n}){let r=e,a=n,{forwardRef:o,currentElement:c}=M(),l=$(),u=We(),d=g(!1);async function f(){let e=c.value;if(!r.disabled&&e){let e=new CustomEvent(we,{bubbles:!0,cancelable:!0});a(`select`,e),await C(),e.defaultPrevented?d.value=!1:l.onClose()}}return(e,n)=>(N(),_(qe,t(r,{ref:i(o),onClick:f,onPointerdown:n[0]||=()=>{d.value=!0},onPointerup:n[1]||=async e=>{await C(),!e.defaultPrevented&&(d.value||e.currentTarget?.click())},onKeydown:n[2]||=async t=>{let n=i(u).searchRef.value!==``;e.disabled||n&&t.key===` `||i(ve).includes(t.key)&&(t.currentTarget?.click(),t.preventDefault())}}),{default:s(()=>[y(e.$slots,`default`)]),_:3},16))}}),Ye=u({__name:`MenuRootContentModal`,props:{loop:{type:Boolean,required:!1},memoDependencies:{type:Array,required:!1},side:{type:null,required:!1},sideOffset:{type:Number,required:!1},sideFlip:{type:Boolean,required:!1},align:{type:null,required:!1},alignOffset:{type:Number,required:!1},alignFlip:{type:Boolean,required:!1},avoidCollisions:{type:Boolean,required:!1},collisionBoundary:{type:null,required:!1},collisionPadding:{type:[Number,Object],required:!1},arrowPadding:{type:Number,required:!1},hideShiftedArrow:{type:Boolean,required:!1},sticky:{type:String,required:!1},hideWhenDetached:{type:Boolean,required:!1},positionStrategy:{type:String,required:!1},updatePositionStrategy:{type:String,required:!1},disableUpdateOnLayoutShift:{type:Boolean,required:!1},prioritizePosition:{type:Boolean,required:!1},reference:{type:null,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1}},emits:[`escapeKeyDown`,`pointerDownOutside`,`focusOutside`,`interactOutside`,`entryFocus`,`openAutoFocus`,`closeAutoFocus`],setup(n,{emit:r}){let a=n,o=r,c=q(a,o),l=Q(),{forwardRef:u,currentElement:d}=M();return ce(d),(n,r)=>(N(),_(Ke,t(i(c),{ref:i(u),"trap-focus":i(l).open.value,"disable-outside-pointer-events":i(l).open.value,"disable-outside-scroll":!0,onDismiss:r[0]||=e=>i(l).onOpenChange(!1),onFocusOutside:r[1]||=e(e=>o(`focusOutside`,e),[`prevent`])}),{default:s(()=>[y(n.$slots,`default`)]),_:3},16,[`trap-focus`,`disable-outside-pointer-events`]))}}),Xe=u({__name:`MenuRootContentNonModal`,props:{loop:{type:Boolean,required:!1},memoDependencies:{type:Array,required:!1},side:{type:null,required:!1},sideOffset:{type:Number,required:!1},sideFlip:{type:Boolean,required:!1},align:{type:null,required:!1},alignOffset:{type:Number,required:!1},alignFlip:{type:Boolean,required:!1},avoidCollisions:{type:Boolean,required:!1},collisionBoundary:{type:null,required:!1},collisionPadding:{type:[Number,Object],required:!1},arrowPadding:{type:Number,required:!1},hideShiftedArrow:{type:Boolean,required:!1},sticky:{type:String,required:!1},hideWhenDetached:{type:Boolean,required:!1},positionStrategy:{type:String,required:!1},updatePositionStrategy:{type:String,required:!1},disableUpdateOnLayoutShift:{type:Boolean,required:!1},prioritizePosition:{type:Boolean,required:!1},reference:{type:null,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1}},emits:[`escapeKeyDown`,`pointerDownOutside`,`focusOutside`,`interactOutside`,`entryFocus`,`openAutoFocus`,`closeAutoFocus`],setup(e,{emit:n}){let r=q(e,n),a=Q();return(e,n)=>(N(),_(Ke,t(i(r),{"trap-focus":!1,"disable-outside-pointer-events":!1,"disable-outside-scroll":!1,onDismiss:n[0]||=e=>i(a).onOpenChange(!1)}),{default:s(()=>[y(e.$slots,`default`)]),_:3},16))}}),Ze=u({__name:`MenuContent`,props:{forceMount:{type:Boolean,required:!1},loop:{type:Boolean,required:!1},memoDependencies:{type:Array,required:!1},side:{type:null,required:!1},sideOffset:{type:Number,required:!1},sideFlip:{type:Boolean,required:!1},align:{type:null,required:!1},alignOffset:{type:Number,required:!1},alignFlip:{type:Boolean,required:!1},avoidCollisions:{type:Boolean,required:!1},collisionBoundary:{type:null,required:!1},collisionPadding:{type:[Number,Object],required:!1},arrowPadding:{type:Number,required:!1},hideShiftedArrow:{type:Boolean,required:!1},sticky:{type:String,required:!1},hideWhenDetached:{type:Boolean,required:!1},positionStrategy:{type:String,required:!1},updatePositionStrategy:{type:String,required:!1},disableUpdateOnLayoutShift:{type:Boolean,required:!1},prioritizePosition:{type:Boolean,required:!1},reference:{type:null,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1}},emits:[`escapeKeyDown`,`pointerDownOutside`,`focusOutside`,`interactOutside`,`entryFocus`,`openAutoFocus`,`closeAutoFocus`],setup(e,{emit:n}){let r=q(e,n),a=Q(),o=$();return(e,n)=>(N(),_(i(oe),{present:e.forceMount||i(a).open.value},{default:s(()=>[i(o).modal.value?(N(),_(Ye,D(t({key:0},{...e.$attrs,...i(r)})),{default:s(()=>[y(e.$slots,`default`)]),_:3},16)):(N(),_(Xe,D(t({key:1},{...e.$attrs,...i(r)})),{default:s(()=>[y(e.$slots,`default`)]),_:3},16))]),_:3},8,[`present`]))}}),Qe=u({__name:`MenuPortal`,props:{to:{type:null,required:!1},disabled:{type:Boolean,required:!1},defer:{type:Boolean,required:!1},forceMount:{type:Boolean,required:!1}},setup(e){let t=e;return(e,n)=>(N(),_(i(he),D(f(t)),{default:s(()=>[y(e.$slots,`default`)]),_:3},16))}}),[$e,et]=K(`DropdownMenuRoot`),tt=u({__name:`DropdownMenuRoot`,props:{defaultOpen:{type:Boolean,required:!1},open:{type:Boolean,required:!1,default:void 0},dir:{type:String,required:!1},modal:{type:Boolean,required:!1,default:!0}},emits:[`update:open`],setup(e,{emit:t}){let n=e,r=t;M();let a=V(n,`open`,r,{defaultValue:n.defaultOpen,passive:n.open===void 0}),o=g(),{modal:c,dir:l}=B(n),u=G(l);return et({open:a,onOpenChange:e=>{a.value=e},onOpenToggle:()=>{a.value=!a.value},triggerId:``,triggerElement:o,contentId:``,modal:c,dir:u}),(e,t)=>(N(),_(i(Ue),{open:i(a),"onUpdate:open":t[0]||=e=>k(a)?a.value=e:null,dir:i(u),modal:i(c)},{default:s(()=>[y(e.$slots,`default`,{open:i(a)})]),_:3},8,[`open`,`dir`,`modal`]))}}),nt=u({__name:`DropdownMenuContent`,props:{forceMount:{type:Boolean,required:!1},loop:{type:Boolean,required:!1},memoDependencies:{type:Array,required:!1},side:{type:null,required:!1},sideOffset:{type:Number,required:!1},sideFlip:{type:Boolean,required:!1},align:{type:null,required:!1},alignOffset:{type:Number,required:!1},alignFlip:{type:Boolean,required:!1},avoidCollisions:{type:Boolean,required:!1},collisionBoundary:{type:null,required:!1},collisionPadding:{type:[Number,Object],required:!1},arrowPadding:{type:Number,required:!1},hideShiftedArrow:{type:Boolean,required:!1},sticky:{type:String,required:!1},hideWhenDetached:{type:Boolean,required:!1},positionStrategy:{type:String,required:!1},updatePositionStrategy:{type:String,required:!1},disableUpdateOnLayoutShift:{type:Boolean,required:!1},prioritizePosition:{type:Boolean,required:!1},reference:{type:null,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1}},emits:[`escapeKeyDown`,`pointerDownOutside`,`focusOutside`,`interactOutside`,`closeAutoFocus`],setup(e,{emit:n}){let r=q(e,n);M();let a=$e(),o=g(!1);function c(e){e.defaultPrevented||(o.value||setTimeout(()=>{a.triggerElement.value?.focus()},0),o.value=!1,e.preventDefault())}return a.contentId||=W(void 0,`reka-dropdown-menu-content`),(e,n)=>(N(),_(i(Ze),t(i(r),{id:i(a).contentId,"aria-labelledby":i(a)?.triggerId,style:{"--reka-dropdown-menu-content-transform-origin":`var(--reka-popper-transform-origin)`,"--reka-dropdown-menu-content-available-width":`var(--reka-popper-available-width)`,"--reka-dropdown-menu-content-available-height":`var(--reka-popper-available-height)`,"--reka-dropdown-menu-trigger-width":`var(--reka-popper-anchor-width)`,"--reka-dropdown-menu-trigger-height":`var(--reka-popper-anchor-height)`},onCloseAutoFocus:c,onInteractOutside:n[0]||=e=>{if(e.defaultPrevented)return;let t=e.detail.originalEvent,n=t.button===0&&t.ctrlKey===!0,r=t.button===2||n;(!i(a).modal.value||r)&&(o.value=!0),i(a).triggerElement.value?.contains(e.target)&&e.preventDefault()}}),{default:s(()=>[y(e.$slots,`default`)]),_:3},16,[`id`,`aria-labelledby`]))}}),rt=u({__name:`DropdownMenuItem`,props:{disabled:{type:Boolean,required:!1},textValue:{type:String,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1}},emits:[`select`],setup(e,{emit:t}){let n=e,r=te(t);return M(),(e,t)=>(N(),_(i(Je),D(f({...n,...i(r)})),{default:s(()=>[y(e.$slots,`default`)]),_:3},16))}}),it=u({__name:`DropdownMenuPortal`,props:{to:{type:null,required:!1},disabled:{type:Boolean,required:!1},defer:{type:Boolean,required:!1},forceMount:{type:Boolean,required:!1}},setup(e){let t=e;return(e,n)=>(N(),_(i(Qe),D(f(t)),{default:s(()=>[y(e.$slots,`default`)]),_:3},16))}}),at=u({__name:`DropdownMenuTrigger`,props:{disabled:{type:Boolean,required:!1},asChild:{type:Boolean,required:!1},as:{type:null,required:!1,default:`button`}},setup(e){let t=e,n=$e(),{forwardRef:r,currentElement:a}=M();return F(()=>{n.triggerElement=a}),n.triggerId||=W(void 0,`reka-dropdown-menu-trigger`),(e,a)=>(N(),_(i(Re),{"as-child":``},{default:s(()=>[o(i(x),{id:i(n).triggerId,ref:i(r),type:e.as===`button`?`button`:void 0,"as-child":t.asChild,as:e.as,"aria-haspopup":`menu`,"aria-expanded":i(n).open.value,"aria-controls":i(n).open.value?i(n).contentId:void 0,"data-disabled":e.disabled?``:void 0,disabled:e.disabled,"data-state":i(n).open.value?`open`:`closed`,onClick:a[0]||=async t=>{!e.disabled&&t.button===0&&t.ctrlKey===!1&&(i(n)?.onOpenToggle(),await C(),i(n).open.value&&t.preventDefault())},onKeydown:a[1]||=d(t=>{e.disabled||([`Enter`,` `].includes(t.key)&&i(n).onOpenToggle(),t.key===`ArrowDown`&&i(n).onOpenChange(!0),[`Enter`,` `,`ArrowDown`].includes(t.key)&&t.preventDefault())},[`enter`,`space`,`arrow-down`])},{default:s(()=>[y(e.$slots,`default`)]),_:3},8,[`id`,`type`,`as-child`,`as`,`aria-expanded`,`aria-controls`,`data-disabled`,`disabled`,`data-state`])]),_:3}))}}),ot=u({__name:`CardContent`,props:{class:{type:[Boolean,null,String,Object,Array]}},setup(e){let t=e;return(e,r)=>(N(),U(`div`,{"data-slot":`card-content`,class:n(i(L)(`px-6`,t.class))},[y(e.$slots,`default`)],2))}}),st=u({__name:`CardHeader`,props:{class:{type:[Boolean,null,String,Object,Array]}},setup(e){let t=e;return(e,r)=>(N(),U(`div`,{"data-slot":`card-header`,class:n(i(L)(`@container/card-header grid auto-rows-min grid-rows-[auto_auto] items-start gap-1.5 px-6 has-data-[slot=card-action]:grid-cols-[1fr_auto] [.border-b]:pb-6`,t.class))},[y(e.$slots,`default`)],2))}}),ct=u({__name:`CardTitle`,props:{class:{type:[Boolean,null,String,Object,Array]}},setup(e){let t=e;return(e,r)=>(N(),U(`h3`,{"data-slot":`card-title`,class:n(i(L)(`leading-none font-semibold`,t.class))},[y(e.$slots,`default`)],2))}}),lt=P(`download`,[[`path`,{d:`M12 15V3`,key:`m9g1x1`}],[`path`,{d:`M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4`,key:`ih7n3h`}],[`path`,{d:`m7 10 5 5 5-5`,key:`brsn70`}]]),ut=P(`ellipsis-vertical`,[[`circle`,{cx:`12`,cy:`12`,r:`1`,key:`41hilf`}],[`circle`,{cx:`12`,cy:`5`,r:`1`,key:`gxeob9`}],[`circle`,{cx:`12`,cy:`19`,r:`1`,key:`lyex9k`}]]),dt=P(`funnel`,[[`path`,{d:`M10 20a1 1 0 0 0 .553.895l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .517-1.341L21.74 4.67A1 1 0 0 0 21 3H3a1 1 0 0 0-.742 1.67l7.225 7.989A2 2 0 0 1 10 14z`,key:`sc7q7i`}]]),ft=P(`refresh-cw`,[[`path`,{d:`M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8`,key:`v9h5vc`}],[`path`,{d:`M21 3v5h-5`,key:`1q7to0`}],[`path`,{d:`M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16`,key:`3uifl3`}],[`path`,{d:`M8 16H3v5`,key:`1cv678`}]]),pt=u({__name:`DropdownMenu`,props:{defaultOpen:{type:Boolean},open:{type:Boolean},dir:{},modal:{type:Boolean}},emits:[`update:open`],setup(e,{emit:n}){let r=q(e,n);return(e,n)=>(N(),_(i(tt),t({"data-slot":`dropdown-menu`},i(r)),{default:s(t=>[y(e.$slots,`default`,D(f(t)))]),_:3},16))}}),mt=u({inheritAttrs:!1,__name:`DropdownMenuContent`,props:{forceMount:{type:Boolean},loop:{type:Boolean},memoDependencies:{},side:{},sideOffset:{default:4},sideFlip:{type:Boolean},align:{},alignOffset:{},alignFlip:{type:Boolean},avoidCollisions:{type:Boolean},collisionBoundary:{},collisionPadding:{},arrowPadding:{},hideShiftedArrow:{type:Boolean},sticky:{},hideWhenDetached:{type:Boolean},positionStrategy:{},updatePositionStrategy:{},disableUpdateOnLayoutShift:{type:Boolean},prioritizePosition:{type:Boolean},reference:{},asChild:{type:Boolean},as:{},class:{type:[Boolean,null,String,Object,Array]}},emits:[`escapeKeyDown`,`pointerDownOutside`,`focusOutside`,`interactOutside`,`closeAutoFocus`],setup(e,{emit:n}){let r=e,c=n,l=a(r,`class`),u=q(l,c);return(e,n)=>(N(),_(i(it),null,{default:s(()=>[o(i(nt),t({"data-slot":`dropdown-menu-content`},{...e.$attrs,...i(u)},{class:i(L)(`bg-popover text-popover-foreground data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 z-50 max-h-(--reka-dropdown-menu-content-available-height) min-w-[8rem] origin-(--reka-dropdown-menu-content-transform-origin) overflow-x-hidden overflow-y-auto rounded-md border p-1 shadow-md`,r.class)}),{default:s(()=>[y(e.$slots,`default`)]),_:3},16,[`class`])]),_:3}))}}),ht=u({__name:`DropdownMenuItem`,props:{disabled:{type:Boolean},textValue:{},asChild:{type:Boolean},as:{},class:{type:[Boolean,null,String,Object,Array]},inset:{type:Boolean},variant:{default:`default`}},setup(e){let n=e,r=a(n,`inset`,`variant`,`class`),o=Y(r);return(r,a)=>(N(),_(i(rt),t({"data-slot":`dropdown-menu-item`,"data-inset":e.inset?``:void 0,"data-variant":e.variant},i(o),{class:i(L)(`focus:bg-accent focus:text-accent-foreground data-[variant=destructive]:text-destructive data-[variant=destructive]:focus:bg-destructive/10 dark:data-[variant=destructive]:focus:bg-destructive/20 data-[variant=destructive]:focus:text-destructive data-[variant=destructive]:*:[svg]:!text-destructive [&_svg:not([class*='text-'])]:text-muted-foreground relative flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-hidden select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[inset]:pl-8 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4`,n.class)}),{default:s(()=>[y(r.$slots,`default`)]),_:3},16,[`data-inset`,`data-variant`,`class`]))}}),gt=u({__name:`DropdownMenuTrigger`,props:{disabled:{type:Boolean},asChild:{type:Boolean},as:{}},setup(e){let n=Y(e);return(e,r)=>(N(),_(i(at),t({"data-slot":`dropdown-menu-trigger`},i(n)),{default:s(()=>[y(e.$slots,`default`)]),_:3},16))}}),_t={class:`min-h-screen p-4 md:p-8`},vt={class:`max-w-5xl mx-auto space-y-8`},yt={class:`text-center space-y-4`},bt={class:`flex items-center justify-center gap-3`},xt={class:`relative`},St={class:`p-4 flex gap-3 items-center`},Ct={class:`p-6`},wt={key:0,class:`flex items-center justify-center py-12`},Tt={key:1,class:`text-center py-12 text-muted-foreground`},Et={key:2,class:`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4`},Dt={class:`flex items-start justify-between`},Ot={class:`flex-1`},kt={class:`text-xs text-muted-foreground`},At={class:`space-y-3`},jt={class:`flex items-center justify-between text-sm`},Mt={class:`text-muted-foreground flex items-center gap-1`},Nt={class:`font-medium`},Pt={class:`flex items-center justify-between`},Ft={class:`text-muted-foreground flex items-center gap-1`},It={class:`text-xl font-bold`},Lt={class:`flex gap-2 pt-2 border-t`},Rt={key:3,class:`flex items-center justify-center gap-2 mt-6`},zt={class:`text-sm text-muted-foreground`},Bt={class:`mb-6 flex flex-wrap items-start justify-between gap-4`},Vt={class:`text-3xl font-bold`},Ht={class:`p-6`},Ut={key:0,class:`flex items-center justify-center py-16`},Wt={key:1,class:`space-y-6`},Gt={class:`grid grid-cols-1 md:grid-cols-2 gap-6`},Kt={class:`border rounded-lg p-4 bg-muted/10`},qt={class:`space-y-1 text-sm`},Jt={key:0,class:`font-medium`},Yt={key:1,class:`text-muted-foreground`},Xt={key:2,class:`mt-3 space-y-1`},Zt={key:0},Qt={key:1},$t={key:2},en={key:3},tn={key:4},nn={key:5},rn={key:6},an={key:7},on={class:`border rounded-lg p-4 bg-muted/10`},sn={key:0,class:`space-y-1 text-sm`},cn={key:0,class:`font-medium`},ln={key:1,class:`font-medium`},un={key:2},dn={key:3},fn={key:4},pn={key:5},mn={key:6},hn={key:7},gn={class:`grid grid-cols-2 md:grid-cols-4 gap-4 text-sm`},_n={class:`mt-0.5`},vn={class:`font-medium mt-0.5`},yn={key:0},bn={class:`font-medium mt-0.5`},xn={class:`font-medium mt-0.5`},Sn={key:0},Cn={class:`overflow-x-auto border rounded-lg`},wn={class:`w-full`},Tn={class:`p-3`},En={class:`p-3 text-right`},Dn={class:`p-3 text-right`},On={class:`p-3 text-right font-medium`},kn={class:`border-t pt-4 space-y-2 max-w-sm ml-auto`},An={class:`flex justify-between`},jn={class:`font-medium`},Mn={class:`flex justify-between`},Nn={class:`text-muted-foreground`},Pn={class:`font-medium`},Fn={class:`flex justify-between text-lg font-bold border-t pt-2`},In={key:1,class:`p-4 bg-muted/30 rounded-lg border`},Ln={class:`text-sm text-muted-foreground`},Rn=c(u({__name:`Invoices`,setup(t){let n=A(),{formatDate:r,formatDateTime:a}=Pe(),{loading:c,getInvoices:u,getInvoice:d}=E(),f=g([]),m=g(1),h=g(1),y=g(`all`),x=g(null),S=g(`list`),C=g(!1),T=e=>{switch(e){case`paid`:return`default`;case`pending`:return`secondary`;case`overdue`:return`destructive`;case`cancelled`:return`outline`;default:return`outline`}},D=async(e=1)=>{m.value=e;try{let t=await u(e,20,y.value===`all`?void 0:y.value);f.value=t.data,h.value=t.meta.pagination.total_pages}catch(e){n.error(e instanceof Error?e.message:`Failed to load invoices`)}},k=async e=>{C.value=!0,S.value=`view`;try{x.value=await d(e)}catch(e){n.error(e instanceof Error?e.message:`Failed to load invoice`),S.value=`list`}finally{C.value=!1}},M=()=>{S.value=`list`,x.value=null},P=e=>e?a(e):`N/A`,I=async e=>{try{let t=e;(!e.items||e.items.length===0)&&(t=await d(e.id));let r=R(t),i=new Blob([r],{type:`text/html`}),a=URL.createObjectURL(i),o=document.createElement(`a`);o.href=a,o.download=`invoice-${t.invoice_number||t.id}.html`,document.body.appendChild(o),o.click(),document.body.removeChild(o),URL.revokeObjectURL(a),n.success(`Invoice downloaded successfully!`)}catch(e){n.error(e instanceof Error?e.message:`Failed to download invoice`)}},L=e=>{if(!e)return``;let t=[];e.full_name&&t.push(e.full_name),e.company_name&&t.push(e.company_name),e.address_line1&&t.push(e.address_line1),e.address_line2&&t.push(e.address_line2);let n=[e.city,e.state,e.postal_code].filter(Boolean).join(`, `);return n&&t.push(n),e.country_code&&t.push(e.country_code),e.vat_id&&t.push(`VAT ID: ${e.vat_id}`),e.phone&&t.push(e.phone),t.join(`<br>`)},R=e=>{let t=e.items?.map(e=>`
      <tr>
        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">${e.description}</td>
        <td style="padding: 8px; text-align: right; border-bottom: 1px solid #e5e7eb;">${e.quantity}</td>
        <td style="padding: 8px; text-align: right; border-bottom: 1px solid #e5e7eb;">${e.unit_price_formatted||e.unit_price}</td>
        <td style="padding: 8px; text-align: right; border-bottom: 1px solid #e5e7eb; font-weight: 600;">${e.total_formatted||e.total}</td>
      </tr>
    `).join(``)||``,n=e.customer?`
      <div class="detail-section">
        <h3>Bill To</h3>
        ${e.customer.username?`<p><strong>${e.customer.username}</strong></p>`:``}
        ${e.customer.email?`<p>${e.customer.email}</p>`:``}
        ${e.customer.billing_info?`<div style="margin-top: 8px;">${L(e.customer.billing_info)}</div>`:``}
      </div>
    `:``,r=e.admin?.billing_info?`
      <div class="detail-section">
        <h3>From</h3>
        ${L(e.admin.billing_info)}
      </div>
    `:``;return`
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Invoice ${e.invoice_number||e.id}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      line-height: 1.6;
      color: #1f2937;
      background: #fff;
      padding: 40px;
    }
    .invoice-container {
      max-width: 800px;
      margin: 0 auto;
      background: #fff;
    }
    .header {
      display: flex;
      justify-content: space-between;
      margin-bottom: 40px;
      padding-bottom: 20px;
      border-bottom: 2px solid #e5e7eb;
    }
    .invoice-title {
      font-size: 32px;
      font-weight: 700;
      color: #111827;
    }
    .invoice-number {
      font-size: 18px;
      color: #6b7280;
      margin-top: 8px;
    }
    .invoice-info {
      text-align: right;
    }
    .status-badge {
      display: inline-block;
      padding: 4px 12px;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 600;
      text-transform: uppercase;
      margin-top: 8px;
    }
    .status-paid { background: #d1fae5; color: #065f46; }
    .status-pending { background: #dbeafe; color: #1e40af; }
    .status-overdue { background: #fee2e2; color: #991b1b; }
    .status-draft { background: #f3f4f6; color: #374151; }
    .status-cancelled { background: #f3f4f6; color: #6b7280; }
    .details {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 30px;
      margin-bottom: 40px;
    }
    .detail-section h3 {
      font-size: 14px;
      font-weight: 600;
      color: #6b7280;
      margin-bottom: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .detail-section p {
      font-size: 16px;
      color: #111827;
      margin-bottom: 4px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 30px;
    }
    thead {
      background: #f9fafb;
    }
    th {
      padding: 12px;
      text-align: left;
      font-size: 12px;
      font-weight: 600;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 2px solid #e5e7eb;
    }
    th.text-right {
      text-align: right;
    }
    .totals {
      margin-top: 20px;
      margin-left: auto;
      width: 300px;
    }
    .total-row {
      display: flex;
      justify-content: space-between;
      padding: 8px 0;
      font-size: 14px;
    }
    .total-row.final {
      border-top: 2px solid #111827;
      margin-top: 8px;
      padding-top: 16px;
      font-size: 20px;
      font-weight: 700;
    }
    .notes {
      margin-top: 40px;
      padding: 20px;
      background: #f9fafb;
      border-radius: 8px;
    }
    .notes h4 {
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 8px;
      color: #111827;
    }
    .notes p {
      font-size: 14px;
      color: #6b7280;
      line-height: 1.6;
    }
    @media print {
      body { padding: 20px; }
      .no-print { display: none; }
    }
  </style>
</head>
<body>
  <div class="invoice-container">
    <div class="header">
      <div>
        <div class="invoice-title">Invoice</div>
        <div class="invoice-number">#${e.invoice_number||e.id}</div>
      </div>
      <div class="invoice-info">
        <div style="font-size: 14px; color: #6b7280;">Status</div>
        <div class="status-badge status-${e.status}">${e.status}</div>
      </div>
    </div>

    <div class="details">
      ${n}
      ${r}
    </div>

    <div class="details" style="margin-top: 20px;">
      <div class="detail-section">
        <h3>Invoice Details</h3>
        <p><strong>Invoice Number:</strong> ${e.invoice_number||e.id}</p>
        <p><strong>Date:</strong> ${P(e.created_at)}</p>
        ${e.due_date?`<p><strong>Due Date:</strong> ${P(e.due_date)}</p>`:``}
        ${e.paid_at?`<p><strong>Paid At:</strong> ${P(e.paid_at)}</p>`:``}
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Description</th>
          <th class="text-right">Quantity</th>
          <th class="text-right">Unit Price</th>
          <th class="text-right">Total</th>
        </tr>
      </thead>
      <tbody>
        ${t}
      </tbody>
    </table>

    <div class="totals">
      <div class="total-row">
        <span>Subtotal:</span>
        <span>${e.subtotal_formatted||e.subtotal}</span>
      </div>
      ${e.tax_rate>0?`
      <div class="total-row">
        <span>Tax (${e.tax_rate}%):</span>
        <span>${e.tax_amount_formatted||e.tax_amount}</span>
      </div>
      `:``}
      <div class="total-row final">
        <span>Total:</span>
        <span>${e.total_formatted||e.total}</span>
      </div>
    </div>

    ${e.notes?`
    <div class="notes">
      <h4>Notes</h4>
      <p>${e.notes}</p>
    </div>
    `:``}
  </div>
</body>
</html>
  `};return F(()=>{D(1)}),(t,n)=>(N(),U(`div`,_t,[w(`div`,vt,[S.value===`list`?(N(),U(v,{key:0},[w(`div`,yt,[w(`div`,bt,[w(`div`,xt,[n[7]||=w(`div`,{class:`absolute inset-0 bg-primary/20 blur-2xl rounded-full`},null,-1),o(i(Ne),{class:`relative h-12 w-12 text-primary`})])]),n[8]||=w(`div`,null,[w(`h1`,{class:`text-5xl font-bold bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent`},` My Invoices `),w(`p`,{class:`text-lg text-muted-foreground mt-2`},` View and manage your invoices `)],-1)]),o(i(b),{class:`border-2 shadow-xl bg-card/50 backdrop-blur-sm`},{default:s(()=>[w(`div`,St,[o(i(dt),{class:`h-4 w-4 text-muted-foreground`}),o(i(fe),{modelValue:y.value,"onUpdate:modelValue":[n[0]||=e=>y.value=e,n[1]||=e=>D(1)]},{default:s(()=>[o(i(Se),{class:`w-[180px]`},{default:s(()=>[o(i(Ee),{placeholder:`All Statuses`})]),_:1}),o(i(ye),null,{default:s(()=>[o(i(X),{value:`all`},{default:s(()=>[...n[9]||=[p(`All Statuses`,-1)]]),_:1}),o(i(X),{value:`draft`},{default:s(()=>[...n[10]||=[p(`Draft`,-1)]]),_:1}),o(i(X),{value:`pending`},{default:s(()=>[...n[11]||=[p(`Pending`,-1)]]),_:1}),o(i(X),{value:`paid`},{default:s(()=>[...n[12]||=[p(`Paid`,-1)]]),_:1}),o(i(X),{value:`overdue`},{default:s(()=>[...n[13]||=[p(`Overdue`,-1)]]),_:1}),o(i(X),{value:`cancelled`},{default:s(()=>[...n[14]||=[p(`Cancelled`,-1)]]),_:1})]),_:1})]),_:1},8,[`modelValue`]),o(i(O),{onClick:n[2]||=e=>D(m.value),variant:`outline`,class:`gap-2`},{default:s(()=>[o(i(ft),{class:`h-4 w-4`}),n[15]||=p(` Refresh `,-1)]),_:1})])]),_:1}),o(i(b),{class:`border-2 shadow-xl bg-card/50 backdrop-blur-sm`},{default:s(()=>[w(`div`,Ct,[i(c)&&f.value.length===0?(N(),U(`div`,wt,[o(i(j),{class:`h-8 w-8 animate-spin`})])):f.value.length===0?(N(),U(`div`,Tt,` No invoices found `)):(N(),U(`div`,Et,[(N(!0),U(v,null,H(f.value,t=>(N(),_(i(b),{key:t.id,class:`hover:shadow-lg transition-shadow cursor-pointer`,onClick:e=>k(t.id)},{default:s(()=>[o(i(st),{class:`pb-3`},{default:s(()=>[w(`div`,Dt,[w(`div`,Ot,[o(i(ct),{class:`text-lg font-semibold mb-1`},{default:s(()=>[p(l(t.invoice_number),1)]),_:2},1024),w(`p`,kt,l(i(r)(t.created_at)),1)]),o(i(Me),{variant:T(t.status),class:`shrink-0`},{default:s(()=>[p(l(t.status),1)]),_:2},1032,[`variant`])])]),_:2},1024),o(i(ot),{class:`pt-0`},{default:s(()=>[w(`div`,At,[w(`div`,jt,[w(`span`,Mt,[o(i(Ce),{class:`h-3 w-3`}),n[16]||=p(` Due Date `,-1)]),w(`span`,Nt,l(i(r)(t.due_date)),1)]),w(`div`,Pt,[w(`span`,Ft,[o(i(re),{class:`h-4 w-4`}),n[17]||=p(` Total `,-1)]),w(`span`,It,l(t.total_formatted||t.total),1)]),w(`div`,Lt,[o(i(O),{onClick:e(e=>k(t.id),[`stop`]),variant:`outline`,size:`sm`,class:`flex-1`},{default:s(()=>[o(i(se),{class:`h-3 w-3 mr-1`}),n[18]||=p(` View `,-1)]),_:1},8,[`onClick`]),o(i(pt),null,{default:s(()=>[o(i(gt),{"as-child":``},{default:s(()=>[o(i(O),{onClick:n[3]||=e(()=>{},[`stop`]),variant:`outline`,size:`sm`,class:`px-2`},{default:s(()=>[o(i(ut),{class:`h-3 w-3`})]),_:1})]),_:1}),o(i(mt),{align:`end`},{default:s(()=>[o(i(ht),{onClick:e(e=>I(t),[`stop`])},{default:s(()=>[o(i(lt),{class:`h-4 w-4 mr-2`}),n[19]||=p(` Download Invoice `,-1)]),_:1},8,[`onClick`])]),_:2},1024)]),_:2},1024)])])]),_:2},1024)]),_:2},1032,[`onClick`]))),128))])),h.value>1?(N(),U(`div`,Rt,[o(i(O),{onClick:n[4]||=e=>D(m.value-1),disabled:m.value===1,variant:`outline`,size:`sm`},{default:s(()=>[o(i(ne),{class:`h-4 w-4`})]),_:1},8,[`disabled`]),w(`span`,zt,` Page `+l(m.value)+` of `+l(h.value),1),o(i(O),{onClick:n[5]||=e=>D(m.value+1),disabled:m.value===h.value,variant:`outline`,size:`sm`},{default:s(()=>[o(i(ae),{class:`h-4 w-4`})]),_:1},8,[`disabled`])])):z(``,!0)])]),_:1})],64)):S.value===`view`?(N(),U(v,{key:1},[w(`div`,Bt,[w(`div`,null,[w(`button`,{type:`button`,onClick:M,class:`inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4`},[o(i(ee),{class:`h-4 w-4`}),n[20]||=p(` Back to invoices `,-1)]),w(`h1`,Vt,` Invoice: `+l(x.value?.invoice_number??`…`),1),n[21]||=w(`p`,{class:`text-muted-foreground mt-1`},` Invoice details and line items `,-1)]),x.value?(N(),_(i(O),{key:0,onClick:n[6]||=e=>I(x.value),variant:`outline`,class:`gap-2`},{default:s(()=>[o(i(lt),{class:`h-4 w-4`}),n[22]||=p(` Download `,-1)]),_:1})):z(``,!0)]),o(i(b),{class:`border-2 shadow-xl`},{default:s(()=>[w(`div`,Ht,[C.value?(N(),U(`div`,Ut,[o(i(j),{class:`h-8 w-8 animate-spin`})])):x.value?(N(),U(`div`,Wt,[w(`div`,Gt,[w(`div`,Kt,[n[23]||=w(`h3`,{class:`font-semibold mb-3 text-sm uppercase text-muted-foreground`},` Bill To `,-1),w(`div`,qt,[x.value.customer?.username?(N(),U(`p`,Jt,l(x.value.customer.username),1)):z(``,!0),x.value.customer?.email?(N(),U(`p`,Yt,l(x.value.customer.email),1)):z(``,!0),x.value.customer?.billing_info?(N(),U(`div`,Xt,[x.value.customer.billing_info.full_name?(N(),U(`p`,Zt,l(x.value.customer.billing_info.full_name),1)):z(``,!0),x.value.customer.billing_info.company_name?(N(),U(`p`,Qt,l(x.value.customer.billing_info.company_name),1)):z(``,!0),x.value.customer.billing_info.address_line1?(N(),U(`p`,$t,l(x.value.customer.billing_info.address_line1),1)):z(``,!0),x.value.customer.billing_info.address_line2?(N(),U(`p`,en,l(x.value.customer.billing_info.address_line2),1)):z(``,!0),x.value.customer.billing_info.city||x.value.customer.billing_info.state||x.value.customer.billing_info.postal_code?(N(),U(`p`,tn,l([x.value.customer.billing_info.city,x.value.customer.billing_info.state,x.value.customer.billing_info.postal_code].filter(Boolean).join(`, `)),1)):z(``,!0),x.value.customer.billing_info.country_code?(N(),U(`p`,nn,l(x.value.customer.billing_info.country_code),1)):z(``,!0),x.value.customer.billing_info.vat_id?(N(),U(`p`,rn,` VAT ID: `+l(x.value.customer.billing_info.vat_id),1)):z(``,!0),x.value.customer.billing_info.phone?(N(),U(`p`,an,l(x.value.customer.billing_info.phone),1)):z(``,!0)])):z(``,!0)])]),w(`div`,on,[n[24]||=w(`h3`,{class:`font-semibold mb-3 text-sm uppercase text-muted-foreground`},` From `,-1),x.value.admin?.billing_info?(N(),U(`div`,sn,[x.value.admin.billing_info.full_name?(N(),U(`p`,cn,l(x.value.admin.billing_info.full_name),1)):z(``,!0),x.value.admin.billing_info.company_name?(N(),U(`p`,ln,l(x.value.admin.billing_info.company_name),1)):z(``,!0),x.value.admin.billing_info.address_line1?(N(),U(`p`,un,l(x.value.admin.billing_info.address_line1),1)):z(``,!0),x.value.admin.billing_info.address_line2?(N(),U(`p`,dn,l(x.value.admin.billing_info.address_line2),1)):z(``,!0),x.value.admin.billing_info.city||x.value.admin.billing_info.state||x.value.admin.billing_info.postal_code?(N(),U(`p`,fn,l([x.value.admin.billing_info.city,x.value.admin.billing_info.state,x.value.admin.billing_info.postal_code].filter(Boolean).join(`, `)),1)):z(``,!0),x.value.admin.billing_info.country_code?(N(),U(`p`,pn,l(x.value.admin.billing_info.country_code),1)):z(``,!0),x.value.admin.billing_info.vat_id?(N(),U(`p`,mn,` VAT ID: `+l(x.value.admin.billing_info.vat_id),1)):z(``,!0),x.value.admin.billing_info.phone?(N(),U(`p`,hn,l(x.value.admin.billing_info.phone),1)):z(``,!0)])):z(``,!0)])]),w(`div`,gn,[w(`div`,null,[n[25]||=w(`span`,{class:`text-muted-foreground`},`Status`,-1),w(`div`,_n,[o(i(Me),{variant:T(x.value.status)},{default:s(()=>[p(l(x.value.status),1)]),_:1},8,[`variant`])])]),w(`div`,null,[n[26]||=w(`span`,{class:`text-muted-foreground`},`Due Date`,-1),w(`div`,vn,l(i(r)(x.value.due_date)),1)]),x.value.paid_at?(N(),U(`div`,yn,[n[27]||=w(`span`,{class:`text-muted-foreground`},`Paid At`,-1),w(`div`,bn,l(i(r)(x.value.paid_at)),1)])):z(``,!0),w(`div`,null,[n[28]||=w(`span`,{class:`text-muted-foreground`},`Created`,-1),w(`div`,xn,l(i(r)(x.value.created_at)),1)])]),x.value.items&&x.value.items.length>0?(N(),U(`div`,Sn,[n[30]||=w(`h3`,{class:`font-semibold mb-3`},`Items`,-1),w(`div`,Cn,[w(`table`,wn,[n[29]||=w(`thead`,null,[w(`tr`,{class:`border-b bg-muted/30`},[w(`th`,{class:`text-left p-3 text-sm font-medium`},`Description`),w(`th`,{class:`text-right p-3 text-sm font-medium`},`Quantity`),w(`th`,{class:`text-right p-3 text-sm font-medium`},`Unit Price`),w(`th`,{class:`text-right p-3 text-sm font-medium`},`Total`)])],-1),w(`tbody`,null,[(N(!0),U(v,null,H(x.value.items,e=>(N(),U(`tr`,{key:e.id,class:`border-b last:border-b-0`},[w(`td`,Tn,l(e.description),1),w(`td`,En,l(e.quantity),1),w(`td`,Dn,l(e.unit_price_formatted||e.unit_price),1),w(`td`,On,l(e.total_formatted||e.total),1)]))),128))])])])])):z(``,!0),w(`div`,kn,[w(`div`,An,[n[31]||=w(`span`,{class:`text-muted-foreground`},`Subtotal:`,-1),w(`span`,jn,l(x.value.subtotal_formatted||x.value.subtotal),1)]),w(`div`,Mn,[w(`span`,Nn,`Tax (`+l(x.value.tax_rate)+`%):`,1),w(`span`,Pn,l(x.value.tax_amount_formatted||x.value.tax_amount),1)]),w(`div`,Fn,[n[32]||=w(`span`,null,`Total:`,-1),w(`span`,null,l(x.value.total_formatted||x.value.total),1)])]),x.value.notes?(N(),U(`div`,In,[n[33]||=w(`h4`,{class:`font-semibold mb-2`},`Notes`,-1),w(`p`,Ln,l(x.value.notes),1)])):z(``,!0)])):z(``,!0)])]),_:1})],64)):z(``,!0)])]))}}));Rn.use(I,{transition:`Vue-Toastification__bounce`,maxToasts:20,newestOnTop:!0});function zn(e){e===`dark`?document.documentElement.classList.add(`dark`):document.documentElement.classList.remove(`dark`)}window.addEventListener(`message`,e=>{e.data?.type===`featherpanel-theme`&&zn(e.data.theme)}),window.parent!==window&&window.parent.postMessage({type:`featherpanel-ready`},`*`),zn(`dark`),document.body.style.background=`transparent`,document.documentElement.style.background=`transparent`,document.body.parentElement&&(document.body.parentElement.style.background=`transparent`),Rn.mount(`#app`);