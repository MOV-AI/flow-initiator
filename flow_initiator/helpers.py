""" Module with methods to help on data manipulation """


def flatten(data: dict, output: list, path: str, join_char: str = ".") -> list:
    """
    Returns a list of paths

    Parameters:
        data (dict): expects a dictionary to start
        output (list): variable to save the list of paths
        path (str): accumulative path
        join_char (str): character to join path entries

    Returns:
        output (list): a list of paths
    """
    if isinstance(data, (dict, list)):
        for key in data:

            if isinstance(data, dict):
                flatten(data[key], output, path + f"{key}{join_char}", join_char)

            else:
                output.append(path + f"{key}")

    else:
        output.append(path + f"{data}")

    return output
