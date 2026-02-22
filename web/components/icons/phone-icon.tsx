"use client";

import { forwardRef, useImperativeHandle, useCallback } from "react";
import type { AnimatedIconHandle, AnimatedIconProps } from "./types";
import { useAnimate } from "motion/react";

const PhoneIcon = forwardRef<AnimatedIconHandle, AnimatedIconProps>(
  (
    {
      size = 24,
      color = "currentColor",
      strokeWidth = 2,
      className = "",
      ...rest
    },
    ref
  ) => {
    const [scope, animate] = useAnimate();

    const start = useCallback(async () => {
      await animate(
        ".phone-handset",
        { rotate: [0, -8, 8, 0], scale: 1.05 },
        { duration: 0.4, ease: "easeOut" }
      );
    }, [animate]);

    const stop = useCallback(async () => {
      await animate(
        ".phone-handset",
        { rotate: 0, scale: 1 },
        { duration: 0.25, ease: "easeInOut" }
      );
    }, [animate]);

    useImperativeHandle(ref, () => ({
      startAnimation: start,
      stopAnimation: stop,
    }));

    const s = typeof size === "number" ? `${size}px` : size;
    return (
      <svg
        ref={scope}
        width={s}
        height={s}
        viewBox="0 0 24 24"
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        {...rest}
      >
        <g className="phone-handset" style={{ transformOrigin: "center center" }}>
          <path d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
        </g>
      </svg>
    );
  }
);

PhoneIcon.displayName = "PhoneIcon";
export default PhoneIcon;
