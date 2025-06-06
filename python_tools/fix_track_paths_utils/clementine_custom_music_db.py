from pathlib import Path
from sys import exit

import pandas as pd
from python_tools.utils.music_db_utils import file_url_to_path
from python_tools.utils.music_db_utils import MERGE_COLS
from python_tools.utils.music_db_utils import open_mixxx_library
from python_tools.utils.music_db_utils import open_table_as_df
from python_tools.utils.music_db_utils import write_df_to_table
from python_tools.utils.track_utils import get_closest_matches_indices
from python_tools.utils.track_utils import remove_feat

from .config import CLEM_DB
from .config import CUSTOM_DB
from .config import CUSTOM_DB_DIRECTORY_COLUMN
from .config import CUSTOM_DB_FILENAME_COLUMN
from .config import CUSTOM_DB_LIBRARY_IDX_COLUMN
from .config import CUSTOM_DB_LOCATION_IDX_COLUMN
from .config import CUSTOM_DB_PATH_COLUMN
from .config import CUSTOM_DB_TABLE_NAME
from .config import N_SIMILAR_TRACK_PROPOSAL
from .config import THRESHOLD_NAME_SIMILARITY


def fix_with_clementine_db():
    df_mixxx = open_mixxx_library(existing_tracks=False)
    if len(df_mixxx) == 0:
        print("No missing tracks, congratulation!")
        exit()

    # TODO (YAGNI?): separate the Clementine DB loading/preparation so the rest of the code
    # can be used with any player (factory method?)
    answer = input("Did you refresh Clementine's library (y/*)? ")
    if answer != "y":
        print("Well do it <3")
        exit()

    df_custom = open_table_as_df(CLEM_DB, "songs")

    # %% Changing/modifying the main columns so they fit CUSTOM_DB_COLUMNS

    # we only need to create file_path
    df_custom[CUSTOM_DB_PATH_COLUMN] = df_custom["filename"].apply(file_url_to_path)

    # %% Cleaning the Player's db

    # droping when file does not exist (Clementine can keep the deleted tracks in its db)
    df_custom = df_custom[
        df_custom[CUSTOM_DB_PATH_COLUMN].apply(lambda p: Path(p).exists())
    ]

    # %% Matching the tracks between Mixxx and the music player

    # removing the "feat."  (sometimes in the artist field of one track and the title field of the other)
    for col in ["artist", "title"]:
        df_mixxx[col] = df_mixxx[col].apply(remove_feat)
        df_custom[col] = df_custom[col].apply(remove_feat)

    # TODO: rename instead of copy ?
    # saving the internal track and location ids to fit the final (exported) dataset
    df_mixxx[CUSTOM_DB_LIBRARY_IDX_COLUMN] = df_mixxx["id"]
    df_mixxx[CUSTOM_DB_LOCATION_IDX_COLUMN] = df_mixxx["location"]

    # saving the table indices for post-merge operations
    IDX_MIXXX = "saved_index_mixxx"
    df_mixxx[IDX_MIXXX] = df_mixxx.index
    IDX_CUSTOM = "saved_index_custom"
    df_custom[IDX_CUSTOM] = df_custom.index

    # %%% Perfect match (pm)
    df_custom_pm = pd.merge(
        left=df_custom,
        right=df_mixxx,
        how="inner",
        on=None,
        left_on=MERGE_COLS,
        right_on=MERGE_COLS,
    )

    df_custom_final = df_custom_pm

    # %%% Close match (cm)

    # we work on the tracks with no match (nm)
    df_mixxx_nm = df_mixxx.drop(index=pd.Index(df_custom_pm[IDX_MIXXX]))
    df_custom_nm = df_custom.drop(index=pd.Index(df_custom_pm[IDX_CUSTOM]))

    # finding the closest match (cm) for each Mixxx track
    if len(df_mixxx_nm):
        print(
            f"\n\n{len(df_mixxx_nm)} tracks have not been found: "
            "we find the closest match for each one…"
        )

        # removing the NA values in the columns we are going to use
        df_mixxx_nm[MERGE_COLS] = df_mixxx_nm[MERGE_COLS].fillna("")
        df_custom_nm[MERGE_COLS] = df_custom_nm[MERGE_COLS].fillna("")

        list_idx_cm = []
        for idx_mixxx, row in df_mixxx_nm.sort_values(
            by=["artist", "title"]
        ).iterrows():
            print(
                f"\nFinding the closest match for Mixxx entry {row[MERGE_COLS].to_list()}"
            )
            close_indices = get_closest_matches_indices(
                row,
                df_custom_nm,
                MERGE_COLS,
                THRESHOLD_NAME_SIMILARITY,
                N_SIMILAR_TRACK_PROPOSAL,
            )

            if len(close_indices) == 0:
                print(
                    f"\tCould not find a track with similar name with actual setting "
                    f"of max similarity distance ({THRESHOLD_NAME_SIMILARITY})."
                )
            else:
                ans_check = [""]
                for i, idx in enumerate(close_indices):
                    # test = df_custom.loc[idx, MERGE_COLS].to_list()
                    print(f"\t{i}:\t{df_custom.loc[idx, MERGE_COLS].to_list()}")
                    ans_check.append(str(i))

                while True:
                    ans = input(
                        "Please choose an index or leave empty to skip the operation: "
                    )
                    if ans in ans_check:
                        break

                if ans:
                    idx_custom = close_indices[int(ans)]
                    list_idx_cm.append(
                        [
                            df_mixxx_nm.loc[idx_mixxx, CUSTOM_DB_LIBRARY_IDX_COLUMN],
                            df_mixxx_nm.loc[idx_mixxx, CUSTOM_DB_LOCATION_IDX_COLUMN],
                            df_custom_nm.loc[idx_custom, CUSTOM_DB_PATH_COLUMN],
                        ]
                    )

        df_custom_cm = pd.DataFrame(
            list_idx_cm,
            columns=[
                CUSTOM_DB_LIBRARY_IDX_COLUMN,
                CUSTOM_DB_LOCATION_IDX_COLUMN,
                CUSTOM_DB_PATH_COLUMN,
            ],
        )
        df_custom_final = pd.concat([df_custom_pm, df_custom_cm])

    # %% Final filtering/output
    df_custom_final = df_custom_final[
        [
            CUSTOM_DB_LIBRARY_IDX_COLUMN,
            CUSTOM_DB_LOCATION_IDX_COLUMN,
            CUSTOM_DB_PATH_COLUMN,
        ]
    ].reset_index(drop=True)
    df_custom_final.loc[:, CUSTOM_DB_FILENAME_COLUMN] = df_custom_final[
        CUSTOM_DB_PATH_COLUMN
    ].apply(lambda x: Path(x).name)
    df_custom_final.loc[:, CUSTOM_DB_DIRECTORY_COLUMN] = df_custom_final[
        CUSTOM_DB_PATH_COLUMN
    ].apply(lambda x: Path(x).parent.as_posix())

    write_df_to_table(
        df_custom_final,
        db_path=CUSTOM_DB,
        table_name=CUSTOM_DB_TABLE_NAME,
        overwrite=True,
    )

    print(
        '\n\nIn case of "UNIQUE CONSTRAINT FAILED", here is the table used to merge '
        "(do not forget to check the hidden tracks in Mixxx !):"
    )
    print(df_custom_final)
