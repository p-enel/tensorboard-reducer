import os
from typing import Dict

import pandas as pd
from torch.utils.tensorboard import SummaryWriter


def force_rm_or_raise(path: str, overwrite: bool) -> None:
    """Remove the directory tree below dir if overwrite is True.

    Args:
        dir (str): The directory whose children will be removed if overwrite.
        overwrite (bool): Whether to overwrite existing.

    Raises:
        FileExistsError: If dir exists and not overwrite.
    """
    if os.path.exists(path):  # True if dir is either file or directory

        # for safety, check dir is either TensorBoard run or CSV file
        # to make it harder to delete files not created by this program
        is_csv_file = path.endswith(".csv")
        is_tb_run_dir = os.path.isdir(path) and os.listdir(path)[0].startswith(
            "events.out"
        )

        if overwrite and (is_csv_file or is_tb_run_dir):
            os.system(f"rm -rf {path}")
        elif overwrite:
            ValueError(
                f"Received the overwrite flag but the content of '{path}' does not "
                "look like it was written by this program. Please make sure you really "
                f"want to delete '{path}' and then do so manually."
            )
        else:
            raise FileExistsError(
                f"'{path}' already exists, pass overwrite=True"
                " (-f/--overwrite in CLI) to proceed anyway"
            )


def write_tb_events(
    data_to_write: Dict[str, Dict[str, pd.DataFrame]],
    outdir: str,
    overwrite: bool = False,
) -> None:
    """Writes a dictionary with tags as keys and reduced TensorBoard scalar data as
    values to disk as a new TensorBoard event file in a newly created or overwritten
    `outdir` directory (depending on `overwrite`).

    Inspired by https://stackoverflow.com/a/48774926.

    Args:
        data_to_write (dict[str, dict[str, pd.DataFrame]]): Data to write to disk.
            Assumes 1st-level keys are reduce ops (mean, std, ...) and 2nd-level are
            TensorBoard tags.
        outdir (str): Name of the directory to save the new reduced run data. Will
            have the reduce op name (e.g. '-mean'/'-std') appended.
        overwrite (bool): Whether to overwrite existing reduction directories.
            Defaults to False.
    """
    # handle std reduction separately as we use writer.add_scalars to write mean +/- std
    if "mean" in data_to_write.keys() and "std" in data_to_write.keys():

        std_dict = data_to_write.pop("std")
        mean_dict = data_to_write["mean"]

        std_dir = f"{outdir}-std"

        force_rm_or_raise(std_dir, overwrite)

        writer = SummaryWriter(std_dir)

        for (tag, means), stds in zip(mean_dict.items(), std_dict.values()):
            # we can safely zip(means, stds): they have the same length and same step
            # values because the same data went into both reductions
            for (step, mean), std in zip(means.items(), stds.to_numpy()):
                writer.add_scalars(
                    tag, {"mean+std": mean + std, "mean-std": mean - std}, step
                )

        writer.close()

    # loop over each reduce operation (e.g. mean, min, max, median)
    for op, events_dict in data_to_write.items():

        op_outdir = f"{outdir}-{op}"

        force_rm_or_raise(op_outdir, overwrite)

        writer = SummaryWriter(op_outdir)

        for tag, series in events_dict.items():
            for step, value in series.items():
                writer.add_scalar(tag, value, step)

        # Important for allowing write_events() to overwrite. Without it,
        # try_rmtree will raise OSError: [Errno 16] Device or resource busy
        # trying to delete the existing outdir.
        writer.close()


def write_csv(
    data_to_write: Dict[str, Dict[str, pd.DataFrame]],
    csv_path: str,
    overwrite: bool = False,
) -> None:
    """Writes reduced TensorBoard data passed as dict of dicts to a CSV file.

    Use `pandas.read_csv("path/to/file.csv", header=[0, 1], index_col=0)` to read CSV
    data back into a multi-index dataframe.

    Args:
        data_to_write (dict[str, dict[str, pd.DataFrame]]): Data to write to disk.
            Assumes 1st-level keys are reduce ops (mean, std, ...) and 2nd-level are
            TensorBoard tags.
        csv_path (str): Name of the CSV file to save the new reduced run data.
        overwrite (bool): Whether to overwrite existing reduction directories.
            Defaults to False.
    """
    assert csv_path.endswith(".csv"), f"{csv_path=} should have a .csv extension"

    force_rm_or_raise(csv_path, overwrite)

    # create multi-index dataframe from event data with reduce op names as 1st-level col
    # names and tag names as 2nd level
    dict_of_dfs = {op: pd.DataFrame(dic) for op, dic in data_to_write.items()}
    df = pd.concat(dict_of_dfs, axis=1)
    df.columns = df.columns.swaplevel(0, 1)

    df.index.name = "step"
    df.to_csv(csv_path)
