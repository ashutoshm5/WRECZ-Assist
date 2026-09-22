import svgPaths from "./svg-2g1bfgeli5";
import imgIcons8Settings1002 from "./0562518c500003ec1fad61bdc966af6f71b532d4.png";
import imgIcons8Notification1001 from "./4c0f6170d297af1cf87ccdde4b3498489ea09db8.png";
import imgIcons8Account1001 from "./da37649a586de2327b5a61bc3ef657838dcfc0f8.png";
import imgImage4603 from "./d68274fc3312c0fbce80dcfb6a9b5380c79b9116.png";

function Group() {
  return (
    <button className="absolute contents cursor-pointer left-[1298px] top-[57px]">
      <div className="absolute left-[1298px] size-[27.035px] top-[57px]" data-name="icons8-notification-100 1">
        <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgIcons8Notification1001} />
      </div>
    </button>
  );
}

function Group1() {
  return (
    <button className="absolute contents cursor-pointer left-[1145px] top-[53px]">
      <div className="absolute left-[1145px] size-[34.467px] top-[53px]" data-name="icons8-account-100 1">
        <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgIcons8Account1001} />
      </div>
    </button>
  );
}

export default function Desktop() {
  return (
    <div className="bg-[#d1d1d1] relative size-full" data-name="Desktop - 5">
      <p className="-translate-x-1/2 [word-break:break-word] absolute font-['Bolshoi:Regular',sans-serif] leading-[normal] left-[140px] not-italic text-[46px] text-black text-center top-[40px] tracking-[14.26px] whitespace-nowrap">wrecz</p>
      <button className="absolute block cursor-pointer left-[1219px] size-[31px] top-[56px]" data-name="icons8-settings-100 2">
        <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgIcons8Settings1002} />
      </button>
      <Group />
      <Group1 />
      <div className="absolute h-0 left-0 top-[422.51px] w-[1440px]">
        <div className="absolute inset-[-5.5px_0]">
          <svg className="block size-full" fill="none" height="11.0004" preserveAspectRatio="none" viewBox="0 0 1440 11.0004" width="1440">
            <path d={svgPaths.p27dec580} id="Vector 5700" stroke="black" strokeWidth="11" />
          </svg>
        </div>
      </div>
      <div className="-translate-x-1/2 absolute h-[75px] left-[calc(50%+0.5px)] pointer-events-none rounded-[97px] top-[746px] w-[779px]">
        <div aria-hidden className="absolute bg-[rgba(217,217,217,0.2)] inset-0 rounded-[97px]" />
        <div className="absolute inset-0 rounded-[inherit] shadow-[inset_3px_4px_9.6px_1px_rgba(0,0,0,0.07)]" />
        <div aria-hidden className="absolute border border-[#9c9c9c] border-solid inset-0 rounded-[97px]" />
      </div>
      <p className="[word-break:break-word] absolute font-['Google_Sans:Regular',sans-serif] h-[26px] leading-[normal] left-[367px] not-italic text-[22.286px] text-[rgba(0,0,0,0.7)] top-[770px] w-[107px]">Type here</p>
      <button className="absolute block cursor-pointer left-[1365px] size-[34px] top-[53px]" data-name="image 4603">
        <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgImage4603} />
      </button>
      <div className="absolute h-[47px] left-[997px] top-[765px] w-[56.724px]">
        <div className="absolute bottom-1/4 left-[10.62%] right-[10.62%] top-[3.88%]">
          <svg className="block size-full" fill="none" height="33.4287" preserveAspectRatio="none" viewBox="0 0 44.6811 33.4287" width="44.6811">
            <path d={svgPaths.p2ba60080} id="Polygon 11" stroke="black" strokeWidth="3.24138" />
          </svg>
        </div>
      </div>
    </div>
  );
}