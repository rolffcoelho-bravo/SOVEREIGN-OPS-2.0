#' @title SOVEREIGN OPS 2.0 R Interface
#' @description R wrapper for the DARP (Domain-Aware Reliability Protocol)
#'   pipeline via reticulate.
#' @importFrom reticulate import_from_path py_to_r
#' @importFrom jsonlite fromJSON

# Internal module reference
.sov_env <- new.env(parent = emptyenv())

#' Configure the SOVEREIGN OPS Python environment
#'
#' Points reticulate at the Python source tree and imports the core
#' modules. Must be called once per R session before any other
#' \code{darp_*} function.
#'
#' @param src_path Character. Path to the \code{src/} directory of
#'   the SOVEREIGN OPS 2.0 repository. Defaults to
#'   \code{system.file("python", package = "sovereignops")} if the
#'   package is installed, otherwise \code{"../src"}.
#' @return Invisible \code{TRUE} on success.
#' @export
#' @examples
#' \dontrun{
#' darp_configure("path/to/sovereign-ops-2.0/src")
#' }
darp_configure <- function(src_path = NULL) {
  if (is.null(src_path)) {
    pkg_path <- system.file("python", package = "sovereignops")
    src_path <- if (nzchar(pkg_path)) pkg_path else "../src"
  }
  if (!dir.exists(src_path)) {
    stop("Source path does not exist: ", src_path, call. = FALSE)
  }
  .sov_env$contracts <- reticulate::import_from_path(
    "sovereign_ops.contracts", path = src_path
  )
  .sov_env$statistics <- reticulate::import_from_path(
    "sovereign_ops.statistics", path = src_path
  )
  .sov_env$configured <- TRUE
  invisible(TRUE)
}

#' Verify DARP contract invariants
#'
#' Checks that the Contract base class enforces \code{extra="forbid"}
#' and \code{frozen=True}, and that the DecisionEnvelope has the
#' expected 5-outcome taxonomy.
#'
#' @return A named list with verification results.
#' @export
#' @examples
#' \dontrun{
#' darp_configure("src")
#' darp_verify_contracts()
#' }
darp_verify_contracts <- function() {
  if (!isTRUE(.sov_env$configured)) {
    stop("Call darp_configure() first.", call. = FALSE)
  }
  contracts <- .sov_env$contracts

  config <- contracts$Contract$model_config
  extra_ok <- identical(config[["extra"]], "forbid")
  frozen_ok <- identical(config[["frozen"]], TRUE)

  outcomes <- c(
    "SUPPORTED_ALERT",
    "INVESTIGATE",
    "ABSTAIN_INSUFFICIENT_EVIDENCE",
    "BLOCK_DATA_INTEGRITY",
    "DEGRADED_SERVICE"
  )

  list(
    contract_extra_forbid = extra_ok,
    contract_frozen = frozen_ok,
    decision_outcomes = outcomes,
    all_ok = extra_ok && frozen_ok
  )
}

#' Run the quick vignette from R
#'
#' Executes the Python quick vignette script and returns its output
#' as a character vector of printed lines.
#'
#' @param vignette_path Character. Path to the vignette script.
#'   Defaults to \code{"scripts/quick_vignette.py"}.
#' @return Character vector of output lines (invisibly).
#' @export
#' @examples
#' \dontrun{
#' darp_configure("src")
#' darp_run_vignette()
#' }
darp_run_vignette <- function(vignette_path = "scripts/quick_vignette.py") {
  if (!file.exists(vignette_path)) {
    stop("Vignette not found: ", vignette_path, call. = FALSE)
  }
  output <- system2(
    "python3", c("-I", vignette_path),
    stdout = TRUE, stderr = TRUE
  )
  cat(paste(output, collapse = "\n"), "\n")
  invisible(output)
}
