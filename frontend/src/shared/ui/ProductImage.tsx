import { useState } from "react";
import { FoodArt } from "./FoodArt";

/** Real photo when the item has one, otherwise the category illustration. */
export function ProductImage({
  src,
  category,
  name,
  className = "",
}: {
  src?: string;
  category: string;
  name: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  if (!src || failed)
    return <FoodArt category={category} name={name} className={className} />;
  return (
    <img
      className={`food-art food-photo ${className}`}
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}
