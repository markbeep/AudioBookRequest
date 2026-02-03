import { useState } from "preact/hooks";
import {
  CheckmarkIcon,
  DownloadIcon,
  PhotoOffIcon,
  PlusIcon,
} from "@/components/icons/preact";
import type { AudiobookSearchResult } from "@/client";

export interface BookCardProps {
  book: AudiobookSearchResult;
  baseUrl: string;
  autoStartDownload?: boolean;
  userCanDownload?: boolean;
}

export default function BookCard({
  book,
  baseUrl,
  autoStartDownload = false,
  userCanDownload = false,
}: BookCardProps) {
  const [isRequested, setIsRequested] = useState(
    book.downloaded || book.already_requested,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buttonClass = isRequested
    ? "btn-ghost bg-success text-neutral/20"
    : "btn-info";

  const displayAuthors = book.authors.slice(0, 2);
  const remainingAuthors =
    book.authors.length > 2 ? book.authors.length - 2 : 0;

  const handleRequestClick = async () => {
    if (!book.asin || isLoading || isRequested) return;

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${baseUrl}/search/request/${book.asin}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`Request failed: ${response.statusText}`);
      }

      // Update state on success
      setIsRequested(true);
    } catch (err) {
      console.error("Failed to request book:", err);
      setError("Request failed");

      // Clear error after 3 seconds
      setTimeout(() => setError(null), 3000);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div class="flex flex-col">
      <div class="relative w-32 h-32 sm:w-40 sm:h-40 rounded-md overflow-hidden shadow shadow-black items-center justify-center flex">
        {book.cover_image ? (
          <img
            class="object-cover w-full h-full hover:scale-110 transition-transform duration-500 ease-in-out"
            height="128"
            width="128"
            src={book.cover_image}
            alt={book.title}
          />
        ) : (
          <PhotoOffIcon />
        )}

        {/* Request Button */}
        <button
          class={`absolute top-0 right-0 rounded-none rounded-bl-md btn-sm btn btn-square items-center justify-center flex ${buttonClass}`}
          onClick={handleRequestClick}
          disabled={isRequested || isLoading}
        >
          {isRequested ? (
            <span>
              <CheckmarkIcon />
            </span>
          ) : (
            <span>
              {autoStartDownload && userCanDownload ? (
                <DownloadIcon />
              ) : (
                <PlusIcon />
              )}
            </span>
          )}
        </button>
      </div>

      {/* Book Info */}
      {book.asin ? (
        <a
          class="text-sm text-primary font-bold pt-1"
          title={book.title}
          target="_blank"
          href={`https://audible.com/pd/${book.asin}?ipRedirectOverride=true`}
          style={{
            display: "-webkit-box",
            WebkitLineClamp: "2",
            lineClamp: "2",
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {book.title}
        </a>
      ) : (
        <div
          class="text-sm text-primary font-bold pt-1"
          title={book.title}
          style={{
            display: "-webkit-box",
            WebkitLineClamp: "2",
            lineClamp: "2",
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {book.title}
        </div>
      )}

      {book.subtitle && (
        <div
          class="opacity-60 font-semibold text-xs"
          title={book.subtitle}
          style={{
            display: "-webkit-box",
            WebkitLineClamp: "1",
            lineClamp: "1",
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {book.subtitle}
        </div>
      )}

      <div
        class="text-xs font-semibold"
        title={`Authors: ${book.authors.join(", ")}`}
        style={{
          display: "-webkit-box",
          WebkitLineClamp: "1",
          lineClamp: "1",
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}
      >
        {displayAuthors.map((author, index) => (
          <>
            <a
              href={`${baseUrl}/search?q=${author}`}
              title={`Search for ${author}`}
              class="hover:underline"
            >
              {author}
            </a>
            {index < displayAuthors.length - 1 && index < 1 && ","}
          </>
        ))}
        {remainingAuthors > 0 && (
          <span class="opacity-60">+{remainingAuthors} more</span>
        )}
      </div>

      {book.runtime_length_hrs && (
        <div class="text-xs opacity-60 mt-1">{book.runtime_length_hrs}h</div>
      )}

      {error && <div class="text-error text-xs mt-1">{error}</div>}
    </div>
  );
}
